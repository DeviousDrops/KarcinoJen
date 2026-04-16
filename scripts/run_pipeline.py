"""Unified KarcinoJen pipeline runner for merged Package A+B+C implementation.

Stage mapping in current code:
- Stage 4 retrieval: src/index/page_index.py + src/retrieval/hybrid_retriever.py
- Stage 5 extraction: src/extractor/vlm_client.py + src/extractor/vlm_extractor.py (vlm-live mode)
- Stage 6/7 validation + CoVe: src/validator/svd_validator.py + src/orchestration/cove_loop.py
- Stage 8 synthesis: src/synthesis/synthesize.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import RuntimeConfig, load_runtime_config
from src.extractor.schema_harness import validate_register_extraction
from src.extractor.vlm_client import VLMClient
from src.extractor.vlm_extractor import run_stage5_extraction
from src.index.page_index import PageRecord, load_page_catalog
from src.ingest.pdf_page_renderer import render_pdf_page
from src.orchestration.cove_loop import run_cove_loop
from src.retrieval.hybrid_retriever import retrieve_top_k
from src.validator.svd_validator import load_svd_registers, validate_extraction

DATA_ROOT = ROOT / "data"
MCU_BENCH_DIR = DATA_ROOT / "mcu-bench"
SVD_DIR = DATA_ROOT / "svd"
DATASHEET_DIR = DATA_ROOT / "datasheets"
CONFIG_PATH = ROOT / "configs" / "model_config.json"
PACKAGE_B_FIXTURE = DATA_ROOT / "fixtures" / "package_b" / "package_b_fixture.json"
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "validated_stm32l4.json"
SYNTHESIZE_SCRIPT = ROOT / "src" / "synthesis" / "synthesize.py"
RUNS_ROOT = ROOT / "runs" / "pipeline"


@dataclass(frozen=True)
class QueryRecord:
    record_id: str
    mcu_family: str
    query: str
    source_file: str
    expected_page_id: str | None


@dataclass(frozen=True)
class PreparedExtraction:
    record_id: str
    mcu_family: str
    source_file: str
    source_page_id: str
    query: str
    extraction: dict[str, Any]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_bits(bits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for bit in bits:
        normalized.append(
            {
                "name": bit.get("name", "UNKNOWN"),
                "position": int(bit.get("bit_offset", bit.get("position", 0))),
                "width": int(bit.get("bit_width", bit.get("width", 1))),
                "access": bit.get("access", "RW"),
            }
        )
    return normalized


def _load_queries(query_id: str | None, family: str | None) -> list[QueryRecord]:
    rows = _read_jsonl(MCU_BENCH_DIR / "queries.jsonl")
    out: list[QueryRecord] = []
    for row in rows:
        if query_id and row["id"] != query_id:
            continue
        if family and str(row["mcu_family"]).lower() != family.lower():
            continue
        out.append(
            QueryRecord(
                record_id=str(row["id"]),
                mcu_family=str(row["mcu_family"]),
                query=str(row["query"]),
                source_file=str(row["source_file"]),
                expected_page_id=row.get("expected_page_id"),
            )
        )
    return out


def _build_retrieval_logs(
    queries: list[QueryRecord],
    page_catalog: list[PageRecord],
    runtime_cfg: RuntimeConfig,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, list[PageRecord]]]:
    logs: list[dict[str, Any]] = []
    hit_map: dict[str, list[PageRecord]] = {}

    for query in queries:
        hits = retrieve_top_k(query.query, page_catalog, runtime_cfg.retrieval, top_k)
        pages = [hit.page for hit in hits]
        hit_map[query.record_id] = pages
        logs.append(
            {
                "id": query.record_id,
                "query": query.query,
                "expected_page_id": query.expected_page_id,
                "retrieved": [
                    {
                        "page_id": hit.page.page_id,
                        "source_file": hit.page.source_file,
                        "page_number": hit.page.page_number,
                        "lexical_score": hit.lexical_score,
                        "semantic_score": hit.semantic_score,
                        "rrf_score": hit.rrf_score,
                    }
                    for hit in hits
                ],
            }
        )

    return logs, hit_map


def _prepare_from_ground_truth(queries: list[QueryRecord]) -> list[PreparedExtraction]:
    gt_rows = {row["id"]: row for row in _read_jsonl(MCU_BENCH_DIR / "ground_truth.jsonl")}
    prepared: list[PreparedExtraction] = []

    for query in queries:
        truth_row = gt_rows.get(query.record_id)
        if not truth_row:
            continue
        truth = truth_row["ground_truth"]
        extraction = {
            "peripheral": truth["peripheral"],
            "register_name": truth["register_name"],
            "base_address": truth["base_address"],
            "offset": truth["offset"],
            "bits": _normalize_bits(truth.get("bits", [])),
            "timing_constraints": truth.get("timing_constraints", []),
        }

        prepared.append(
            PreparedExtraction(
                record_id=query.record_id,
                mcu_family=query.mcu_family,
                source_file=query.source_file,
                source_page_id=query.expected_page_id or "unknown",
                query=query.query,
                extraction=extraction,
            )
        )

    return prepared


def _prepare_from_package_b_fixture() -> list[PreparedExtraction]:
    payload = _read_json(PACKAGE_B_FIXTURE)
    prepared: list[PreparedExtraction] = []
    for row in payload["samples"]:
        prepared.append(
            PreparedExtraction(
                record_id=row["id"],
                mcu_family="MockMCU",
                source_file="mock_fixture.pdf",
                source_page_id=f"fixture_{row['id']}",
                query=row["query"],
                extraction=row["v2_output"],
            )
        )
    return prepared


def _prepare_from_demo_fixture() -> list[PreparedExtraction]:
    rows = _read_json(DEMO_FIXTURE)
    prepared: list[PreparedExtraction] = []
    for index, row in enumerate(rows, start=1):
        extraction = {
            "peripheral": row["peripheral"],
            "register_name": row["register_name"],
            "base_address": row["base_address"],
            "offset": row["offset"],
            "bits": row.get("bits", []),
            "timing_constraints": row.get("timing_constraints", []),
        }
        prepared.append(
            PreparedExtraction(
                record_id=f"demo_{index}",
                mcu_family=row.get("mcu_family", "STM32L4"),
                source_file=row.get("source_file", "demo_fixture.pdf"),
                source_page_id=row.get("source_page_id", f"demo_page_{index}"),
                query=f"Demo fixture record {index}",
                extraction=extraction,
            )
        )
    return prepared


def _prepare_from_vlm_live(
    *,
    queries: list[QueryRecord],
    hit_map: dict[str, list[PageRecord]],
    runtime_cfg: RuntimeConfig,
    run_root: Path,
) -> tuple[list[PreparedExtraction], list[dict[str, Any]]]:
    client = VLMClient(runtime_cfg.provider)
    stage5_logs: list[dict[str, Any]] = []
    prepared: list[PreparedExtraction] = []

    rendered_dir = run_root / "A" / "rendered_pages"
    for query in queries:
        top_pages = hit_map.get(query.record_id, [])
        page_context: list[dict[str, Any]] = []
        for page in top_pages:
            pdf_path = DATASHEET_DIR / page.source_file
            image_path = None
            if pdf_path.exists():
                rendered = render_pdf_page(pdf_path, page.page_number, rendered_dir)
                if rendered is not None:
                    image_path = str(rendered)

            page_context.append(
                {
                    "page_id": page.page_id,
                    "source_file": page.source_file,
                    "page_number": page.page_number,
                    "peripheral": page.peripheral,
                    "keywords": page.keywords,
                    "image_path": image_path,
                }
            )

        stage5 = run_stage5_extraction(
            client=client,
            extraction_cfg=runtime_cfg.extraction,
            query=query.query,
            page_context=page_context,
        )

        stage5_logs.append(
            {
                "record_id": query.record_id,
                "status": stage5.status,
                "attempts": [
                    {
                        "attempt": attempt.attempt,
                        "schema_valid": attempt.schema_valid,
                        "schema_errors": attempt.schema_errors,
                        "parsed_json": attempt.parsed_json,
                    }
                    for attempt in stage5.attempts
                ],
            }
        )

        if stage5.status == "PASS" and stage5.extraction is not None:
            source_page_id = page_context[0]["page_id"] if page_context else "unknown"
            source_file = page_context[0]["source_file"] if page_context else query.source_file
            prepared.append(
                PreparedExtraction(
                    record_id=query.record_id,
                    mcu_family=query.mcu_family,
                    source_file=source_file,
                    source_page_id=source_page_id,
                    query=query.query,
                    extraction=stage5.extraction,
                )
            )

    return prepared, stage5_logs


def _svd_path_for_family(family: str) -> Path:
    mapping = {
        "stm32f401": SVD_DIR / "stm32f401.svd",
        "rp2040": SVD_DIR / "RP2040.svd",
        "mockmcu": SVD_DIR / "mock_mcu.svd",
        "stm32l4": SVD_DIR / "mock_mcu.svd",
    }
    return mapping.get(family.lower(), SVD_DIR / "mock_mcu.svd")


def run_pipeline(args: argparse.Namespace) -> Path:
    runtime_cfg = load_runtime_config(CONFIG_PATH)
    run_root = RUNS_ROOT / _utc_stamp()
    run_root.mkdir(parents=True, exist_ok=True)

    top_k = args.top_k or runtime_cfg.retrieval.top_k
    queries = _load_queries(args.query_id, args.family)
    if not queries:
        raise RuntimeError("No query records found for the selected filters")

    page_catalog = load_page_catalog(MCU_BENCH_DIR / "page_catalog.jsonl")
    retrieval_logs, hit_map = _build_retrieval_logs(queries, page_catalog, runtime_cfg, top_k)
    _write_json(run_root / "A" / "retrieval_topk.json", retrieval_logs)

    stage5_logs: list[dict[str, Any]] = []
    if args.mode == "ground-truth":
        prepared = _prepare_from_ground_truth(queries)
    elif args.mode == "package-b-fixture":
        prepared = _prepare_from_package_b_fixture()
    elif args.mode == "demo-fixture":
        prepared = _prepare_from_demo_fixture()
    else:
        prepared, stage5_logs = _prepare_from_vlm_live(
            queries=queries,
            hit_map=hit_map,
            runtime_cfg=runtime_cfg,
            run_root=run_root,
        )
        _write_json(run_root / "B" / "stage5_vlm_logs.json", stage5_logs)

    if not prepared:
        raise RuntimeError("No extraction payloads were produced for this mode")

    b_records: list[dict[str, Any]] = []
    synthesis_input: list[dict[str, Any]] = []

    for item in prepared:
        schema_result = validate_register_extraction(item.extraction)
        svd_path = _svd_path_for_family(item.mcu_family)
        registers = load_svd_registers(str(svd_path))

        if not schema_result.is_valid:
            b_records.append(
                {
                    "record_id": item.record_id,
                    "query": item.query,
                    "mcu_family": item.mcu_family,
                    "svd_file": str(svd_path.relative_to(ROOT).as_posix()),
                    "schema_valid": False,
                    "schema_errors": schema_result.errors,
                    "initial_validation": None,
                    "final_status": "UNCERTAIN",
                    "cove": None,
                }
            )
            continue

        base_validation = validate_extraction(item.extraction, registers)
        cove_attempts = 1
        final_status = base_validation.status
        final_extraction = item.extraction
        cove_payload: dict[str, Any] | None = None

        if base_validation.status != "PASS":
            cove_outcome = run_cove_loop(item.extraction, registers, max_attempts=3)
            cove_attempts = len(cove_outcome.attempts)
            final_status = cove_outcome.status
            final_extraction = cove_outcome.final_extraction
            cove_payload = {
                "status": cove_outcome.status,
                "attempts": cove_outcome.attempts,
            }

        b_records.append(
            {
                "record_id": item.record_id,
                "query": item.query,
                "mcu_family": item.mcu_family,
                "svd_file": str(svd_path.relative_to(ROOT).as_posix()),
                "schema_valid": schema_result.is_valid,
                "schema_errors": schema_result.errors,
                "initial_validation": {
                    "status": base_validation.status,
                    "checks": base_validation.checks,
                    "message": base_validation.message,
                },
                "final_status": final_status,
                "cove": cove_payload,
            }
        )

        if final_status == "PASS":
            synthesis_input.append(
                {
                    "peripheral": final_extraction["peripheral"],
                    "register_name": final_extraction["register_name"],
                    "base_address": final_extraction["base_address"],
                    "offset": final_extraction["offset"],
                    "bits": final_extraction.get("bits", []),
                    "timing_constraints": final_extraction.get("timing_constraints", []),
                    "source_page_id": item.source_page_id,
                    "source_file": item.source_file,
                    "validation_status": "PASS",
                    "validation_attempts": cove_attempts,
                    "mcu_family": item.mcu_family,
                }
            )

    _write_json(run_root / "B" / "validation_summary.json", b_records)

    synthesis_out = run_root / "C" / "synthesis"
    synthesis_out.mkdir(parents=True, exist_ok=True)
    synthesis_input_path = run_root / "B" / "validated_for_synthesis.json"
    _write_json(synthesis_input_path, synthesis_input)

    if synthesis_input:
        synthesis_proc = subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE_SCRIPT),
                "--input",
                str(synthesis_input_path),
                "--outdir",
                str(synthesis_out),
            ],
            capture_output=True,
            text=True,
        )
        _write_json(
            run_root / "C" / "synthesis_run_log.json",
            {
                "return_code": synthesis_proc.returncode,
                "stdout": synthesis_proc.stdout,
                "stderr": synthesis_proc.stderr,
            },
        )
        if synthesis_proc.returncode != 0:
            raise RuntimeError("Synthesis stage failed. See C/synthesis_run_log.json")

    summary = {
        "run_mode": args.mode,
        "selected_query_id": args.query_id,
        "selected_family": args.family,
        "input_hint": args.datasheet,
        "config": {
            "config_path": str(CONFIG_PATH.relative_to(ROOT).as_posix()),
            "version": runtime_cfg.version,
            "provider": runtime_cfg.selected_provider,
            "model": runtime_cfg.provider.model,
            "provider_env": runtime_cfg.provider.api_key_env or runtime_cfg.provider.endpoint_env,
            "extraction": {
                "max_attempts": runtime_cfg.extraction.max_attempts,
                "temperature": runtime_cfg.extraction.temperature,
            },
            "retrieval": {
                "top_k": top_k,
                "lexical_weight": runtime_cfg.retrieval.lexical_weight,
                "semantic_weight": runtime_cfg.retrieval.semantic_weight,
                "hex_token_boost": runtime_cfg.retrieval.hex_token_boost,
                "rrf_k": runtime_cfg.retrieval.rrf_k,
            },
        },
        "counts": {
            "prepared_extractions": len(prepared),
            "schema_valid": sum(1 for row in b_records if row["schema_valid"]),
            "final_pass": sum(1 for row in b_records if row["final_status"] == "PASS"),
            "final_uncertain": sum(1 for row in b_records if row["final_status"] == "UNCERTAIN"),
        },
        "models_used": {
            "retrieval": "hybrid lexical-semantic with RRF",
            "vlm": runtime_cfg.provider.model if args.mode == "vlm-live" else "not called",
            "llm": "not called separately; same VLM endpoint used for extraction",
            "cove": "deterministic correction loop (no external model call)",
        },
        "artifacts": {
            "retrieval_log": "A/retrieval_topk.json",
            "validation_summary": "B/validation_summary.json",
            "validated_for_synthesis": "B/validated_for_synthesis.json",
            "synthesis_dir": "C/synthesis",
            "stage5_vlm_logs": "B/stage5_vlm_logs.json" if stage5_logs else None,
        },
    }
    _write_json(run_root / "summary.json", summary)
    return run_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run integrated KarcinoJen pipeline")
    parser.add_argument(
        "--mode",
        choices=["ground-truth", "package-b-fixture", "demo-fixture", "vlm-live"],
        default="ground-truth",
        help="Extraction source mode",
    )
    parser.add_argument("--query-id", default=None, help="Optional query id filter")
    parser.add_argument("--family", default=None, help="Optional MCU family filter")
    parser.add_argument("--datasheet", default=None, help="Optional datasheet path hint for metadata")
    parser.add_argument("--top-k", type=int, default=None, help="Top-k retrieval results")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_root = run_pipeline(args)
    print(f"Integrated pipeline complete. Artifacts: {run_root}")


if __name__ == "__main__":
    main()
