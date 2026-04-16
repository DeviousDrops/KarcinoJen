"""Unified KarcinoJen pipeline runner for merged Package A+B+C artifacts.

This script integrates currently implemented pieces:
- Package A data artifacts (queries, page catalog, ground truth)
- Package B schema/validator/CoVe logic
- Package C synthesis outputs

It does not call external VLM/LLM APIs in the current repo state.
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

from src.extractor.schema_harness import validate_register_extraction
from src.orchestration.cove_loop import run_cove_loop
from src.validator.svd_validator import load_svd_registers, validate_extraction

DATA_ROOT = ROOT / "data"
MCU_BENCH_DIR = DATA_ROOT / "mcu-bench"
SVD_DIR = DATA_ROOT / "svd"
PACKAGE_B_FIXTURE = DATA_ROOT / "fixtures" / "package_b" / "package_b_fixture.json"
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "validated_stm32l4.json"
SYNTHESIZE_SCRIPT = ROOT / "src" / "synthesis" / "synthesize.py"
RUNS_ROOT = ROOT / "runs" / "pipeline"


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
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_bits(bits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bit in bits:
        out.append(
            {
                "name": bit.get("name", "UNKNOWN"),
                "position": int(bit.get("bit_offset", bit.get("position", 0))),
                "width": int(bit.get("bit_width", bit.get("width", 1))),
                "access": bit.get("access", "RW"),
            }
        )
    return out


def _simple_retrieval_score(query: str, page_keywords: list[str]) -> int:
    q_tokens = {token.lower() for token in query.replace("_", " ").split()}
    score = 0
    for keyword in page_keywords:
        k = keyword.lower()
        if k in q_tokens:
            score += 3
        elif any(token in k or k in token for token in q_tokens):
            score += 1
    return score


def _run_placeholder_retrieval(
    queries: list[dict[str, Any]], pages: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query_record in queries:
        ranked = sorted(
            pages,
            key=lambda page: _simple_retrieval_score(query_record["query"], page.get("keywords", [])),
            reverse=True,
        )
        top = ranked[:top_k]
        rows.append(
            {
                "id": query_record["id"],
                "query": query_record["query"],
                "expected_page_id": query_record.get("expected_page_id"),
                "retrieved": [
                    {
                        "page_id": page["page_id"],
                        "source_file": page["source_file"],
                        "page_number": page["page_number"],
                        "score": _simple_retrieval_score(query_record["query"], page.get("keywords", [])),
                    }
                    for page in top
                ],
            }
        )
    return rows


def _prepare_from_ground_truth(
    query_id: str | None,
    family_filter: str | None,
) -> list[PreparedExtraction]:
    queries = _read_jsonl(MCU_BENCH_DIR / "queries.jsonl")
    gt_records = {row["id"]: row for row in _read_jsonl(MCU_BENCH_DIR / "ground_truth.jsonl")}

    prepared: list[PreparedExtraction] = []
    for query in queries:
        if query_id and query["id"] != query_id:
            continue
        if family_filter and query["mcu_family"].lower() != family_filter.lower():
            continue
        gt = gt_records.get(query["id"])
        if not gt:
            continue

        truth = gt["ground_truth"]
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
                record_id=query["id"],
                mcu_family=query["mcu_family"],
                source_file=query["source_file"],
                source_page_id=query.get("expected_page_id", "unknown"),
                query=query["query"],
                extraction=extraction,
            )
        )

    return prepared


def _prepare_from_package_b_fixture() -> list[PreparedExtraction]:
    fixture = _read_json(PACKAGE_B_FIXTURE)
    prepared: list[PreparedExtraction] = []
    for item in fixture["samples"]:
        prepared.append(
            PreparedExtraction(
                record_id=item["id"],
                mcu_family="MockMCU",
                source_file="mock_fixture.pdf",
                source_page_id=f"fixture_{item['id']}",
                query=item["query"],
                extraction=item["v2_output"],
            )
        )
    return prepared


def _prepare_from_demo_fixture() -> list[PreparedExtraction]:
    rows = _read_json(DEMO_FIXTURE)
    prepared: list[PreparedExtraction] = []
    for idx, row in enumerate(rows, start=1):
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
                record_id=f"demo_{idx}",
                mcu_family=row.get("mcu_family", "STM32L4"),
                source_file=row.get("source_file", "demo_fixture.pdf"),
                source_page_id=row.get("source_page_id", f"demo_page_{idx}"),
                query=f"Demo fixture record {idx}",
                extraction=extraction,
            )
        )
    return prepared


def _svd_path_for_family(family: str) -> Path:
    mapping = {
        "stm32f401": SVD_DIR / "stm32f401.svd",
        "rp2040": SVD_DIR / "RP2040.svd",
        "mockmcu": SVD_DIR / "mock_mcu.svd",
        "stm32l4": SVD_DIR / "mock_mcu.svd",
    }
    key = family.lower()
    if key in mapping:
        return mapping[key]
    return SVD_DIR / "mock_mcu.svd"


def run_pipeline(args: argparse.Namespace) -> Path:
    run_root = RUNS_ROOT / _utc_stamp()
    run_root.mkdir(parents=True, exist_ok=True)

    queries = _read_jsonl(MCU_BENCH_DIR / "queries.jsonl")
    pages = _read_jsonl(MCU_BENCH_DIR / "page_catalog.jsonl")
    retrieval_log = _run_placeholder_retrieval(queries, pages, args.top_k)
    _write_json(run_root / "A" / "retrieval_topk.json", retrieval_log)

    if args.mode == "ground-truth":
        extracted = _prepare_from_ground_truth(args.query_id, args.family)
    elif args.mode == "package-b-fixture":
        extracted = _prepare_from_package_b_fixture()
    else:
        extracted = _prepare_from_demo_fixture()

    if not extracted:
        raise RuntimeError("No extraction candidates found for selected mode/filter.")

    b_records: list[dict[str, Any]] = []
    synthesis_input: list[dict[str, Any]] = []

    for item in extracted:
        schema_result = validate_register_extraction(item.extraction)
        svd_path = _svd_path_for_family(item.mcu_family)
        registers = load_svd_registers(str(svd_path))

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
        result = subprocess.run(
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
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )
        if result.returncode != 0:
            raise RuntimeError("Synthesis step failed. See C/synthesis_run_log.json")

    summary = {
        "run_mode": args.mode,
        "selected_query_id": args.query_id,
        "selected_family": args.family,
        "input_hint": args.datasheet,
        "counts": {
            "prepared_extractions": len(extracted),
            "schema_valid": sum(1 for row in b_records if row["schema_valid"]),
            "final_pass": sum(1 for row in b_records if row["final_status"] == "PASS"),
            "final_uncertain": sum(1 for row in b_records if row["final_status"] == "UNCERTAIN"),
        },
        "models_used": {
            "retrieval": "keyword baseline from page catalog (placeholder for hybrid retrieval)",
            "vlm": "none in current codebase (extraction simulated from fixtures/ground truth)",
            "llm": "none in current codebase",
            "cove": "deterministic correction loop (no external model call)",
        },
        "artifacts": {
            "retrieval_log": "A/retrieval_topk.json",
            "validation_summary": "B/validation_summary.json",
            "validated_for_synthesis": "B/validated_for_synthesis.json",
            "synthesis_dir": "C/synthesis",
        },
    }
    _write_json(run_root / "summary.json", summary)
    return run_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run integrated KarcinoJen pipeline")
    parser.add_argument(
        "--mode",
        choices=["ground-truth", "package-b-fixture", "demo-fixture"],
        default="ground-truth",
        help="Extraction source mode",
    )
    parser.add_argument("--query-id", default=None, help="Optional query id filter for ground-truth mode")
    parser.add_argument("--family", default=None, help="Optional MCU family filter for ground-truth mode")
    parser.add_argument("--datasheet", default=None, help="Optional datasheet path hint for run metadata")
    parser.add_argument("--top-k", type=int, default=3, help="Top-k pages to keep in retrieval logs")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_root = run_pipeline(args)
    print(f"Integrated pipeline complete. Artifacts: {run_root}")


if __name__ == "__main__":
    main()
