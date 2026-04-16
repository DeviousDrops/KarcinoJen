"""Generate a C++ driver from one datasheet and one user query.

The supported flow is only:
- input: datasheet path + natural-language query
- processing: retrieval -> VLM extraction -> validation -> synthesis
- output: driver.h and driver.c
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import load_runtime_config
from src.extractor.vlm_client import VLMClient
from src.extractor.vlm_extractor import run_stage5_extraction
from src.ingest.pdf_page_renderer import render_pdf_page
from src.retrieval.chroma_retriever import retrieve_top_pages
from src.validator.svd_validator import load_svd_registers

DATA_ROOT = ROOT / "data"
DATASHEET_DIR = DATA_ROOT / "datasheets"
SVD_DIR = DATA_ROOT / "svd"
CONFIG_PATH = ROOT / "configs" / "model_config.json"
SYNTHESIZE_SCRIPT = ROOT / "src" / "synthesis" / "synthesize.py"
DEFAULT_OUTDIR = ROOT / "generated" / "drivers"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_datasheet_path(raw_value: str) -> Path:
    candidate = Path(raw_value)
    if candidate.exists():
        return candidate.resolve()

    bundled = DATASHEET_DIR / raw_value
    if bundled.exists():
        return bundled.resolve()

    raise FileNotFoundError(f"Could not find datasheet: {raw_value}")


def _resolve_svd_path(datasheet_path: Path) -> Path:
    stem = datasheet_path.stem.lower()
    if "stm32f401" in stem:
        return SVD_DIR / "stm32f401.svd"
    if "rp2040" in stem:
        return SVD_DIR / "RP2040.svd"
    return SVD_DIR / "mock_mcu.svd"


def _family_name(datasheet_path: Path) -> str:
    stem = datasheet_path.stem.lower()
    if "stm32f401" in stem:
        return "STM32F401"
    if "rp2040" in stem:
        return "RP2040"
    return datasheet_path.stem.upper()


def _build_page_context(datasheet_path: Path, top_pages: list[dict[str, object]], render_dir: Path) -> list[dict[str, object]]:
    page_context: list[dict[str, object]] = []
    for page in top_pages:
        rendered = render_pdf_page(datasheet_path, int(page["page_number"]), render_dir)
        page_context.append(
            {
                "page_id": page["page_id"],
                "source_file": page["source_file"],
                "page_number": page["page_number"],
                "peripheral": page["peripheral"],
                "keywords": page["keywords"],
                "page_text": page.get("text", ""),
                "image_path": str(rendered) if rendered is not None else None,
            }
        )
    return page_context


def _run_synthesis(validated_payload: dict[str, object], outdir: Path) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        input_path = temp_root / "validated.json"
        input_path.write_text(json.dumps([validated_payload], indent=2), encoding="utf-8")

        return subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE_SCRIPT),
                "--input",
                str(input_path),
                "--outdir",
                str(outdir),
                "--audit-trace",
            ],
            capture_output=True,
            text=True,
        )


def _enrich_driver_with_groq(
    validated_payload: dict[str, object],
    outdir: Path,
    groq_client: VLMClient,
) -> None:
    """Use Groq to generate an enriched driver.c with application guidance.

    Reads the template-generated driver.c and the validated register JSON,
    then asks Groq to produce an improved version with proper init logic,
    usage comments, and bit-manipulation helpers.
    """
    driver_c_path = outdir / "driver.c"
    driver_h_path = outdir / "driver.h"
    if not driver_c_path.exists() or not driver_h_path.exists():
        return

    template_c = driver_c_path.read_text(encoding="utf-8")
    template_h = driver_h_path.read_text(encoding="utf-8")

    groq_prompt = (
        "You are an embedded-systems C code generator.\n"
        "You are given a register extraction JSON and a template driver skeleton.\n"
        "Produce a complete, compilable driver.c that:\n"
        "  1. Includes driver.h\n"
        "  2. Implements each _init(), _read(), and _write() stub with correct\n"
        "     bit-field manipulation using the #defines from driver.h\n"
        "  3. Adds a brief inline comment per function explaining what the register does\n"
        "  4. Does NOT change the #defines in driver.h\n"
        "Return ONLY the C source code as plain text. No markdown fences."
    )

    evidence = json.dumps(
        {
            "validated_extraction": validated_payload,
            "template_driver_h": template_h,
            "template_driver_c": template_c,
        },
        indent=2,
    )

    # Groq uses the OpenAI-compatible text path; send as a plain text page.
    page_context = [
        {
            "page_id": validated_payload.get("source_page_id", "extracted"),
            "page_text": evidence,
        }
    ]

    try:
        response = groq_client.extract(
            prompt_text=groq_prompt,
            query="Generate enriched driver.c",
            page_context=page_context,
            mismatch_report=None,
        )
        # Groq returns JSON per our client contract; but for code generation
        # we want raw text. Try to extract a 'code' or 'driver_c' key,
        # or fall back to the full raw_text if it looks like C code.
        raw = response.raw_text.strip()
        if raw.startswith("#include") or "void " in raw:
            driver_c_path.write_text(raw, encoding="utf-8")
            print("[groq] driver.c enriched by Groq synthesis.")
        elif isinstance(response.parsed_json, dict):
            code = (
                response.parsed_json.get("driver_c")
                or response.parsed_json.get("code")
                or response.parsed_json.get("content")
            )
            if code and isinstance(code, str) and "#include" in code:
                driver_c_path.write_text(code, encoding="utf-8")
                print("[groq] driver.c enriched by Groq synthesis.")
            else:
                print("[groq] Groq response did not contain valid C code; keeping template.")
    except Exception as exc:
        # Groq enrichment is best-effort; do not fail the whole pipeline.
        print(f"[groq] Enrichment skipped: {exc}")


def run_pipeline(args: argparse.Namespace) -> Path:
    runtime_cfg = load_runtime_config(CONFIG_PATH)
    datasheet_path = _resolve_datasheet_path(args.datasheet)
    if args.top_k is not None:
        # Keep CLI override behavior while still using configured backend and fusion weights.
        retrieval_cfg = runtime_cfg.retrieval.__class__(
            top_k=args.top_k,
            lexical_weight=runtime_cfg.retrieval.lexical_weight,
            semantic_weight=runtime_cfg.retrieval.semantic_weight,
            hex_token_boost=runtime_cfg.retrieval.hex_token_boost,
            rrf_k=runtime_cfg.retrieval.rrf_k,
            backend=runtime_cfg.retrieval.backend,
            chroma_path=runtime_cfg.retrieval.chroma_path,
            collection_prefix=runtime_cfg.retrieval.collection_prefix,
            embedding_model=runtime_cfg.retrieval.embedding_model,
            semantic_candidates_multiplier=runtime_cfg.retrieval.semantic_candidates_multiplier,
        )
    else:
        retrieval_cfg = runtime_cfg.retrieval

    top_pages = retrieve_top_pages(
        query=args.query,
        datasheet_path=datasheet_path,
        retrieval_cfg=retrieval_cfg,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        page_context = _build_page_context(datasheet_path, top_pages, temp_root / "rendered_pages")
        if not page_context:
            raise RuntimeError("No page context could be built for the selected datasheet")

        svd_path = _resolve_svd_path(datasheet_path)
        registers = load_svd_registers(str(svd_path))
        client = VLMClient(runtime_cfg.provider)

        # Build fallback clients for the VLM extraction stage.
        #
        # Primary = gemini  →  fallback: groq (text-only, reliable, same free tier)
        # Primary = llava   →  fallback: ollama (text) then groq
        # Primary = groq    →  no extraction fallback (groq is already the fallback tier)
        #
        # Groq also runs a best-effort driver.c enrichment pass after synthesis.
        fallback_clients: list[VLMClient] = []
        selected = runtime_cfg.selected_provider

        if selected == "gemini":
            groq_fb = runtime_cfg.providers.get("groq")
            if groq_fb is not None:
                fallback_clients.append(VLMClient(groq_fb))

        elif selected == "llava":
            ollama_fb = runtime_cfg.providers.get("ollama")
            if ollama_fb is not None:
                fallback_clients.append(VLMClient(ollama_fb))
            groq_fb = runtime_cfg.providers.get("groq")
            if groq_fb is not None:
                fallback_clients.append(VLMClient(groq_fb))


        stage5 = run_stage5_extraction(
            client=client,
            fallback_clients=fallback_clients or None,
            extraction_cfg=runtime_cfg.extraction,
            query=args.query,
            page_context=page_context,
            registers=registers,
        )

        if stage5.status != "PASS" or stage5.extraction is None:
            raise RuntimeError("Extraction could not be validated after retries")

        first_page = top_pages[0] if top_pages else None
        validated_payload = {
            **stage5.extraction,
            "validation_status": "PASS",
            "validation_attempts": len(stage5.attempts),
            "source_page_id": first_page["page_id"] if first_page else "unknown",
            "source_file": datasheet_path.name,
            "mcu_family": _family_name(datasheet_path),
        }

        outdir = args.outdir / _utc_stamp()
        outdir.mkdir(parents=True, exist_ok=True)

        synthesis_proc = _run_synthesis(validated_payload, outdir)
        if synthesis_proc.returncode != 0:
            raise RuntimeError(
                "Synthesis failed: "
                f"{synthesis_proc.stderr.strip() or synthesis_proc.stdout.strip()}"
            )

        if not (outdir / "driver.h").exists() or not (outdir / "driver.c").exists():
            raise RuntimeError("Synthesis completed but driver files were not created")

        # Groq enrichment pass: ask Groq to generate a complete, annotated driver.c
        # from the validated schema + template skeleton.  This is the primary use of
        # the Groq API key and is the architectural step described in the README.
        groq_provider = runtime_cfg.providers.get("groq")
        if groq_provider is not None:
            groq_client = VLMClient(groq_provider)
            _enrich_driver_with_groq(validated_payload, outdir, groq_client)

        print(f"Query: {args.query}")
        print(f"Datasheet: {datasheet_path}")
        print(f"Driver output: {outdir}")
        return outdir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a C++ driver from a datasheet and query")
    parser.add_argument("--datasheet", required=True, help="Datasheet path or bundled filename")
    parser.add_argument("--query", required=True, help="Natural-language extraction request")
    parser.add_argument(
        "--outdir",
        default=str(DEFAULT_OUTDIR),
        help="Directory under which a timestamped driver folder will be created",
    )
    parser.add_argument("--top-k", type=int, default=None, help="Number of retrieved pages to feed into the VLM context")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.outdir = Path(args.outdir)
    run_pipeline(args)


if __name__ == "__main__":
    main()
