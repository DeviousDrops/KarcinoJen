"""Run Member 2 Package B modules B1->B5 with deterministic fixtures."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.prompt_bank import COVE_PROMPT_TEMPLATE, PROMPT_V1, PROMPT_V2
from src.extractor.schema_harness import validate_register_extraction
from src.orchestration.cove_loop import run_cove_loop
from src.validator.error_taxonomy import classify_failure
from src.validator.svd_validator import load_svd_registers, validate_extraction

FIXTURE_PATH = ROOT / "data" / "fixtures" / "package_b" / "package_b_fixture.json"
SVD_PATH = ROOT / "data" / "svd" / "mock_mcu.svd"
ARTIFACT_ROOT = ROOT / "artifacts" / "package_b"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    path.write_text(content + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def run_b1(fixture: dict[str, Any], run_root: Path) -> dict[str, Any]:
    module_root = run_root / "B1"
    _write_text(module_root / "prompt_v1.txt", PROMPT_V1 + "\n")

    logs: list[dict[str, Any]] = []
    for sample in fixture["samples"]:
        result = validate_register_extraction(sample["v1_output"])
        logs.append(
            {
                "sample_id": sample["id"],
                "schema_valid": result.is_valid,
                "errors": result.errors,
                "output": sample["v1_output"],
            }
        )

    valid_count = sum(1 for item in logs if item["schema_valid"])
    summary = {
        "module": "B1",
        "total": len(logs),
        "valid": valid_count,
        "validity_rate": valid_count / len(logs),
        "done_check": "end-to-end extraction run completes",
    }

    _write_json(module_root / "extraction_run_log.json", {"summary": summary, "logs": logs})
    return summary


def run_b2(fixture: dict[str, Any], run_root: Path) -> dict[str, Any]:
    module_root = run_root / "B2"
    _write_text(module_root / "prompt_v2.txt", PROMPT_V2 + "\n")

    logs: list[dict[str, Any]] = []
    valid_outputs: list[dict[str, Any]] = []

    for sample in fixture["samples"]:
        result = validate_register_extraction(sample["v2_output"])
        logs.append(
            {
                "sample_id": sample["id"],
                "schema_valid": result.is_valid,
                "errors": result.errors,
                "output": sample["v2_output"],
            }
        )
        if result.is_valid:
            valid_outputs.append({"sample_id": sample["id"], "output": sample["v2_output"]})

    valid_count = sum(1 for item in logs if item["schema_valid"])
    validity_rate = valid_count / len(logs)

    if validity_rate < 0.8:
        raise RuntimeError(f"B2 done check failed: schema-valid rate {validity_rate:.2%} < 80%")

    notes = (
        "Prompt tuning notes\n"
        "- v2 adds strict type/format constraints and JSON-only guardrails.\n"
        "- v2 explicitly disallows guessed values and malformed bit entries.\n"
        f"- Outcome: {valid_count}/{len(logs)} schema-valid ({validity_rate:.2%}).\n"
    )

    _write_text(module_root / "prompt_iteration_notes.md", notes)
    _write_json(module_root / "schema_validation_log.json", {"logs": logs, "validity_rate": validity_rate})
    _write_jsonl(module_root / "schema_valid_outputs.jsonl", valid_outputs)

    return {
        "module": "B2",
        "total": len(logs),
        "valid": valid_count,
        "validity_rate": validity_rate,
        "done_check": ">=80 percent schema-valid JSON on sample set",
    }


def run_b3(fixture: dict[str, Any], run_root: Path) -> dict[str, Any]:
    module_root = run_root / "B3"
    registers = load_svd_registers(str(SVD_PATH))

    reports: list[dict[str, Any]] = []
    caught = 0

    for case in fixture["injected_failures"]:
        validation = validate_extraction(case["output"], registers)
        checks = validation.checks
        fail_detected = validation.status == "FAIL"
        if fail_detected:
            caught += 1

        reports.append(
            {
                "case_id": case["id"],
                "expected_failure_type": case["expected_failure_type"],
                "status": validation.status,
                "checks": checks,
                "message": validation.message,
            }
        )

    if caught != len(fixture["injected_failures"]):
        raise RuntimeError("B3 done check failed: not all injected failures were caught")

    _write_json(module_root / "validator_mismatch_reports.json", {"reports": reports})

    return {
        "module": "B3",
        "injected_cases": len(fixture["injected_failures"]),
        "caught": caught,
        "done_check": "injected address/bit errors are detected",
    }


def run_b4(fixture: dict[str, Any], run_root: Path) -> dict[str, Any]:
    module_root = run_root / "B4"
    registers = load_svd_registers(str(SVD_PATH))

    retry_logs: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []

    for case in fixture["cove_cases"]:
        outcome = run_cove_loop(case["initial_output"], registers, max_attempts=3)
        retry_logs.append(
            {
                "case_id": case["id"],
                "attempts": outcome.attempts,
                "final_status": outcome.status,
            }
        )
        outcomes.append(
            {
                "case_id": case["id"],
                "expected_outcome": case["expected_outcome"],
                "actual_outcome": outcome.status,
                "final_output": outcome.final_extraction,
            }
        )

    for item in outcomes:
        if item["expected_outcome"] != item["actual_outcome"]:
            raise RuntimeError(
                f"B4 done check failed: {item['case_id']} expected {item['expected_outcome']} got {item['actual_outcome']}"
            )

    _write_text(module_root / "cove_prompt_template.txt", COVE_PROMPT_TEMPLATE + "\n")
    _write_json(module_root / "retry_logs.json", {"cases": retry_logs})
    _write_json(module_root / "final_outcomes.json", {"cases": outcomes})

    corrected = sum(1 for item in outcomes if item["actual_outcome"] == "PASS")
    uncertain = sum(1 for item in outcomes if item["actual_outcome"] == "UNCERTAIN")
    return {
        "module": "B4",
        "cases": len(outcomes),
        "corrected": corrected,
        "uncertain": uncertain,
        "done_check": "max 3 retries and deterministic fail-closed behavior",
    }


def run_b5(run_root: Path) -> dict[str, Any]:
    module_root = run_root / "B5"

    b3_reports = json.loads((run_root / "B3" / "validator_mismatch_reports.json").read_text(encoding="utf-8"))["reports"]
    b4_logs = json.loads((run_root / "B4" / "retry_logs.json").read_text(encoding="utf-8"))["cases"]

    evidence_rows: list[dict[str, Any]] = []

    for report in b3_reports:
        category = classify_failure(report["checks"])
        evidence_rows.append(
            {
                "source": "B3",
                "id": report["case_id"],
                "category": category,
                "validator_caught": report["status"] == "FAIL",
                "snippet": report["message"],
            }
        )

    for run in b4_logs:
        if run["final_status"] == "PASS":
            continue

        last_attempt = run["attempts"][-1]
        checks = last_attempt["validation"]["checks"]
        category = classify_failure(checks)
        evidence_rows.append(
            {
                "source": "B4",
                "id": run["case_id"],
                "category": category,
                "validator_caught": True,
                "snippet": last_attempt["validation"]["message"],
            }
        )

    coverage = {"Address Drift": 0, "Layout Confusion": 0, "Context Bleed": 0}
    for row in evidence_rows:
        if row["category"] in coverage:
            coverage[row["category"]] += 1

    markdown_lines = [
        "# Package B Taxonomy Evidence",
        "",
        "| Source | ID | Category | Validator Caught | Evidence Snippet |",
        "|---|---|---|---|---|",
    ]

    for row in evidence_rows:
        markdown_lines.append(
            f"| {row['source']} | {row['id']} | {row['category']} | {row['validator_caught']} | {row['snippet']} |"
        )

    markdown_lines += [
        "",
        "## Coverage",
        f"- Address Drift: {coverage['Address Drift']}",
        f"- Layout Confusion: {coverage['Layout Confusion']}",
        f"- Context Bleed: {coverage['Context Bleed']}",
    ]

    _write_json(module_root / "taxonomy_evidence.json", {"rows": evidence_rows, "coverage": coverage})
    _write_text(module_root / "taxonomy_evidence.md", "\n".join(markdown_lines) + "\n")

    if not all(coverage[key] >= 1 for key in coverage):
        raise RuntimeError("B5 done check failed: missing at least one required taxonomy category")

    return {
        "module": "B5",
        "rows": len(evidence_rows),
        "coverage": coverage,
        "done_check": "taxonomy table and evidence snippets are paper-ready",
    }


def write_status(run_root: Path, current_module: str, summary: dict[str, Any], artifacts: list[Path]) -> None:
    status_text = (
        f"- Current module: {current_module}\n"
        f"- Scope completed: {summary}\n"
        "- Open risk: Synthetic fixtures may not represent full retrieval variance.\n"
        "- Next exact command/action: python scripts/run_package_b.py\n"
        "- Artifact paths produced:\n"
        + "\n".join(f"  - {path.relative_to(ROOT).as_posix()}" for path in artifacts)
        + "\n"
    )
    _write_text(run_root / "status.md", status_text)


def run_package_b() -> Path:
    fixture = _load_fixture()
    run_root = ARTIFACT_ROOT / _utc_stamp()
    run_root.mkdir(parents=True, exist_ok=True)

    b1_summary = run_b1(fixture, run_root)
    write_status(run_root, "B1", b1_summary, [run_root / "B1" / "extraction_run_log.json"])

    b2_summary = run_b2(fixture, run_root)
    write_status(run_root, "B2", b2_summary, [run_root / "B2" / "schema_valid_outputs.jsonl"])

    b3_summary = run_b3(fixture, run_root)
    write_status(run_root, "B3", b3_summary, [run_root / "B3" / "validator_mismatch_reports.json"])

    b4_summary = run_b4(fixture, run_root)
    write_status(run_root, "B4", b4_summary, [run_root / "B4" / "retry_logs.json", run_root / "B4" / "final_outcomes.json"])

    b5_summary = run_b5(run_root)
    write_status(run_root, "B5", b5_summary, [run_root / "B5" / "taxonomy_evidence.md", run_root / "B5" / "taxonomy_evidence.json"])

    return run_root


if __name__ == "__main__":
    output_path = run_package_b()
    print(f"Package B completed. Artifacts: {output_path}")
