"""Generate a C driver from one datasheet and one user query.

The supported flow is:
- input: datasheet path + natural-language query
- processing: retrieval (ColPali/lexical) → VLM extraction → SVD validation → CoVe → synthesis
- output: driver.h, driver.c, and audit_trace.json
"""

from __future__ import annotations

import argparse
import json
import os
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
from src.retrieval.hybrid_retriever import retrieve_top_pages
from src.synthesis.llm_enrichment import enrich_driver_with_fallback
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


def _build_page_context(
    datasheet_path: Path,
    top_pages: list[dict[str, object]],
    render_dir: Path,
) -> list[dict[str, object]]:
    page_context: list[dict[str, object]] = []
    for page in top_pages:
        # Check if ColPali retriever already provided an image path
        image_path = page.get("image_path")
        if not image_path or not Path(str(image_path)).exists():
            rendered = render_pdf_page(datasheet_path, int(page["page_number"]), render_dir)
            image_path = str(rendered) if rendered is not None else None

        page_context.append(
            {
                "page_id": page["page_id"],
                "source_file": page.get("source_file", datasheet_path.name),
                "page_number": page["page_number"],
                "peripheral": page.get("peripheral", ""),
                "keywords": page.get("keywords", []),
                "page_text": page.get("text", ""),
                "image_path": str(image_path) if image_path else None,
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


def _build_extraction_fallback_clients(runtime_cfg) -> list[VLMClient]:
    # Local VLM fallbacks were intentionally removed.
    # Stage 5 now uses OCR fallback when the primary VLM cannot produce
    # a schema-valid + SVD-valid extraction.
    return []


def _build_enrichment_clients(runtime_cfg) -> list[VLMClient]:
    clients: list[VLMClient] = []
    for provider_name in ("groq", "openai"):
        provider_cfg = runtime_cfg.providers.get(provider_name)
        if provider_cfg is not None:
            clients.append(VLMClient(provider_cfg))
    return clients


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
            colpali_model=runtime_cfg.retrieval.colpali_model,
            colpali_index_path=runtime_cfg.retrieval.colpali_index_path,
        )
    else:
        retrieval_cfg = runtime_cfg.retrieval

    print(f"[pipeline] Retrieval backend: {retrieval_cfg.backend}")
    print(f"[pipeline] Provider: {runtime_cfg.selected_provider}/{runtime_cfg.provider.model}")

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

        fallback_clients = _build_extraction_fallback_clients(runtime_cfg)

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

        # Best-effort LLM enrichment with local fallback chain.
        enriched, provider_or_reason = enrich_driver_with_fallback(
            validated_payload=validated_payload,
            driver_h_path=outdir / "driver.h",
            driver_c_path=outdir / "driver.c",
            clients=_build_enrichment_clients(runtime_cfg),
        )
        if enriched:
            print(f"[llm] driver.c enriched via {provider_or_reason}")
        else:
            print(f"[llm] enrichment skipped: {provider_or_reason}")

        print(f"Query: {args.query}")
        print(f"Datasheet: {datasheet_path}")
        print(f"Driver output: {outdir}")
        return outdir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a C driver from a datasheet and query")
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
