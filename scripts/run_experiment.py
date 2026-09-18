#!/usr/bin/env python3
"""Run the 3-configuration experiment for KarcinoJen paper evaluation.

Configurations:
  1. Vanilla VLM   — VLM extraction only, no SVD validation, no CoVe
  2. KarcinoJen−CoVe — SVD validation enabled, CoVe loop disabled
  3. Full KarcinoJen — SVD validation + CoVe loop (max 3 retries)

Runs each configuration against the MCU-Bench dataset and reports:
  - PASS@K (address accuracy)
  - Extraction validity rate
  - CoVe recovery rate
  - Error taxonomy breakdown

Usage:
    python scripts/run_experiment.py
    python scripts/run_experiment.py --config vanilla
    python scripts/run_experiment.py --benchmark data/mcu-bench/benchmark.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import load_runtime_config
from src.extractor.vlm_client import VLMClient
from src.extractor.vlm_extractor import run_stage5_extraction
from src.extractor.schema_harness import validate_register_extraction
from src.ingest.pdf_page_renderer import render_pdf_page
from src.retrieval.hybrid_retriever import retrieve_top_pages
from src.validator.svd_validator import load_svd_registers, validate_extraction
from src.validator.error_taxonomy import classify_failure
from src.synthesis.synthesize import _synthesize_register, _write_driver_h, _write_driver_c
from src.evaluation.pass_at_k import (
    BenchmarkResult,
    ConfigResults,
    compute_pass_at_k,
    evaluate_extraction_against_ground_truth,
    generate_experiment_report,
)

CONFIG_PATH = ROOT / "configs" / "model_config.json"
DEFAULT_BENCHMARK = ROOT / "data" / "mcu-bench" / "benchmark.json"
DEFAULT_OUTDIR = ROOT / "runs" / "experiments"

# Rate limit sleep between API calls (seconds)
API_SLEEP_SECONDS = 4


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_benchmark(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["records"]


def _build_page_context(
    datasheet_path: Path,
    top_pages: list[dict[str, Any]],
    render_dir: Path,
) -> list[dict[str, Any]]:
    page_context: list[dict[str, Any]] = []
    for page in top_pages:
        rendered = render_pdf_page(datasheet_path, int(page["page_number"]), render_dir)
        page_context.append({
            "page_id": page["page_id"],
            "source_file": page["source_file"],
            "page_number": page["page_number"],
            "peripheral": page.get("peripheral", ""),
            "keywords": page.get("keywords", []),
            "page_text": str(page.get("text", ""))[:4000],
            "image_path": str(rendered) if rendered else page.get("image_path"),
        })
    return page_context


def run_single_query(
    *,
    record: dict[str, Any],
    config_name: str,
    runtime_cfg: Any,
    enable_validation: bool,
    enable_cove: bool,
) -> BenchmarkResult:
    """Run a single benchmark query through one pipeline configuration."""
    query_id = record["id"]
    query = record["query"]
    ground_truth = record.get("ground_truth") or record.get("ground_truth_json") or {}
    ds_stem = record["datasheet_stem"]
    svd_stem = record["svd_stem"]

    t0 = time.perf_counter()

    try:
        ds_path = ROOT / "data" / "datasheets" / f"{ds_stem}.pdf"
        svd_path = ROOT / "data" / "svd" / f"{svd_stem}.svd"

        if not ds_path.exists():
            return BenchmarkResult(
                query_id=query_id, query=query, config_name=config_name,
                extraction_status="FAIL", extraction_attempts=0, schema_valid=False,
                svd_checks=None, address_correct=False, bit_fields_correct=False,
                name_correct=False, timing_valid=None, error_category=None,
                cove_recovered=False, elapsed_s=0, extracted_json=None,
                ground_truth=ground_truth,
            )

        # ── Retrieval ────────────────────────────────────────────────────
        top_pages = retrieve_top_pages(
            query=query, datasheet_path=ds_path, retrieval_cfg=runtime_cfg.retrieval
        )

        if not top_pages:
            return BenchmarkResult(
                query_id=query_id, query=query, config_name=config_name,
                extraction_status="FAIL", extraction_attempts=0, schema_valid=False,
                svd_checks=None, address_correct=False, bit_fields_correct=False,
                name_correct=False, timing_valid=None, error_category=None,
                cove_recovered=False, elapsed_s=time.perf_counter() - t0,
                extracted_json=None, ground_truth=ground_truth,
            )

        # ── Build context ────────────────────────────────────────────────
        with tempfile.TemporaryDirectory() as td:
            render_dir = Path(td) / "rendered"
            page_context = _build_page_context(ds_path, top_pages, render_dir)

            registers = load_svd_registers(str(svd_path)) if enable_validation else None
            client = VLMClient(runtime_cfg.provider)

            # Adjust extraction config based on configuration
            extraction_cfg = runtime_cfg.extraction
            if not enable_cove:
                # Disable retries for no-CoVe config
                extraction_cfg = copy.copy(extraction_cfg)
                object.__setattr__(extraction_cfg, "max_attempts", 1)

            stage5 = run_stage5_extraction(
                client=client,
                extraction_cfg=extraction_cfg,
                query=query,
                page_context=page_context,
                registers=registers if enable_validation else None,
            )

            extraction = stage5.extraction
            schema_valid = extraction is not None and \
                validate_register_extraction(extraction).is_valid if extraction else False

            # ── Evaluate against ground truth ────────────────────────────
            address_correct = False
            bit_fields_correct = False
            name_correct = False
            error_category = None
            svd_checks = None
            cove_recovered = False
            pass_k_accuracy = None

            if extraction is not None:
                gt_eval = evaluate_extraction_against_ground_truth(extraction, ground_truth)
                address_correct = gt_eval["address_correct"]
                bit_fields_correct = gt_eval["bit_fields_correct"]
                name_correct = gt_eval["name_correct"]

                if enable_validation and registers:
                    val_result = validate_extraction(extraction, registers)
                    svd_checks = val_result.checks
                    if val_result.status != "PASS":
                        error_category = classify_failure(val_result.checks)

                # Synthesize and compute PASS@K from generated driver.h addresses.
                validated_payload = {
                    **extraction,
                    "validation_status": "PASS",
                    "validation_attempts": len(stage5.attempts),
                    "source_page_id": top_pages[0]["page_id"],
                    "source_file": ds_path.name,
                    "mcu_family": svd_stem.upper(),
                }
                synth = _synthesize_register(validated_payload)
                if synth is not None:
                    out_dir = Path(td) / "synth"
                    out_dir.mkdir(exist_ok=True)
                    h_path = out_dir / "driver.h"
                    c_path = out_dir / "driver.c"
                    _write_driver_h([synth], str(h_path))
                    _write_driver_c([synth], "driver.h", str(c_path))

                    pass_report = compute_pass_at_k(
                        h_path,
                        svd_path,
                        peripheral_filter=record.get("peripheral"),
                    )
                    pass_k_accuracy = float(pass_report.get("accuracy", 0.0))

                    total_defines = int(pass_report.get("total_defines", 0))
                    matched = int(pass_report.get("matched", 0))
                    if total_defines > 0:
                        address_correct = matched == total_defines

                # Check if CoVe recovered
                if enable_cove and len(stage5.attempts) > 1:
                    first_attempt = stage5.attempts[0]
                    if first_attempt.validation_status != "PASS" and stage5.status == "PASS":
                        cove_recovered = True

            elapsed = time.perf_counter() - t0

            return BenchmarkResult(
                query_id=query_id, query=query, config_name=config_name,
                extraction_status=stage5.status,
                extraction_attempts=len(stage5.attempts),
                schema_valid=schema_valid, svd_checks=svd_checks,
                address_correct=address_correct,
                bit_fields_correct=bit_fields_correct,
                name_correct=name_correct, timing_valid=None,
                error_category=error_category,
                cove_recovered=cove_recovered,
                elapsed_s=round(elapsed, 2),
                extracted_json=extraction,
                ground_truth=ground_truth,
                pass_k_accuracy=pass_k_accuracy,
            )

    except Exception as exc:
        if "--verbose" in sys.argv:
            traceback.print_exc()
        return BenchmarkResult(
            query_id=query_id, query=query, config_name=config_name,
            extraction_status="FAIL", extraction_attempts=0, schema_valid=False,
            svd_checks=None, address_correct=False, bit_fields_correct=False,
            name_correct=False, timing_valid=None,
            error_category=None, cove_recovered=False,
            elapsed_s=round(time.perf_counter() - t0, 2),
            extracted_json=None, ground_truth=ground_truth,
        )


EXPERIMENT_CONFIGS = [
    {
        "name": "vanilla_vlm",
        "label": "Baseline 1: Vanilla VLM",
        "enable_validation": False,
        "enable_cove": False,
    },
    {
        "name": "karcinojen_no_cove",
        "label": "Baseline 2: KarcinoJen−CoVe",
        "enable_validation": True,
        "enable_cove": False,
    },
    {
        "name": "full_karcinojen",
        "label": "Proposed: Full KarcinoJen",
        "enable_validation": True,
        "enable_cove": True,
    },
]


def run_experiment(
    *,
    benchmark_path: Path,
    outdir: Path,
    configs_to_run: list[str] | None = None,
) -> dict[str, Any]:
    """Run the full experiment across selected configurations."""
    runtime_cfg = load_runtime_config(CONFIG_PATH)
    records = _load_benchmark(benchmark_path)

    print(f"\n{'='*72}")
    print(f"  KarcinoJen Experiment Runner")
    print(f"  Provider: {runtime_cfg.selected_provider} / {runtime_cfg.provider.model}")
    print(f"  Benchmark: {benchmark_path.name} ({len(records)} queries)")
    print(f"{'='*72}")

    all_config_results: list[ConfigResults] = []

    for exp_cfg in EXPERIMENT_CONFIGS:
        if configs_to_run and exp_cfg["name"] not in configs_to_run:
            continue

        config_name = exp_cfg["name"]
        label = exp_cfg["label"]
        enable_validation = exp_cfg["enable_validation"]
        enable_cove = exp_cfg["enable_cove"]

        print(f"\n{'─'*72}")
        print(f"  Running: {label}")
        print(f"  Validation: {'ON' if enable_validation else 'OFF'} | "
              f"CoVe: {'ON' if enable_cove else 'OFF'}")
        print(f"{'─'*72}")

        cfg_results = ConfigResults(config_name=config_name)

        for i, record in enumerate(records, 1):
            print(f"  [{i}/{len(records)}] {record['peripheral']}.{record['register']} ...",
                  end="", flush=True)

            result = run_single_query(
                record=record,
                config_name=config_name,
                runtime_cfg=runtime_cfg,
                enable_validation=enable_validation,
                enable_cove=enable_cove,
            )
            cfg_results.results.append(result)

            status = "✓" if result.address_correct else "✗"
            print(f" {status} addr={'OK' if result.address_correct else 'FAIL'} "
                  f"[{result.extraction_status}, {result.elapsed_s}s]")

            # Rate limit sleep
            if i < len(records):
                time.sleep(API_SLEEP_SECONDS)

        print(f"\n  Config Summary: {cfg_results.summary_dict()}")
        all_config_results.append(cfg_results)

    # ── Generate report ──────────────────────────────────────────────────
    report = generate_experiment_report(all_config_results)
    report["timestamp"] = _utc_stamp()
    report["benchmark_file"] = str(benchmark_path)
    report["provider"] = f"{runtime_cfg.selected_provider}/{runtime_cfg.provider.model}"

    # Add per-query details
    report["detailed_results"] = {}
    for cfg_results in all_config_results:
        report["detailed_results"][cfg_results.config_name] = [
            {
                "query_id": r.query_id,
                "query": r.query,
                "extraction_status": r.extraction_status,
                "extraction_attempts": r.extraction_attempts,
                "schema_valid": r.schema_valid,
                "address_correct": r.address_correct,
                "pass_at_k": r.pass_k_accuracy,
                "name_correct": r.name_correct,
                "bit_fields_correct": r.bit_fields_correct,
                "error_category": r.error_category,
                "cove_recovered": r.cove_recovered,
                "elapsed_s": r.elapsed_s,
            }
            for r in cfg_results.results
        ]

    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / f"experiment_{_utc_stamp()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ── Print comparison table ───────────────────────────────────────────
    print(f"\n{'='*72}")
    print("  EXPERIMENT RESULTS")
    print(f"{'='*72}")
    print(f"  {'Config':<30s} {'Pass%':>7s} {'Valid%':>7s} {'P@K%':>7s} {'CoVe%':>7s} {'Errors':>10s}")
    print(f"  {'─'*30} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*10}")

    for cfg in all_config_results:
        s = cfg.summary_dict()
        taxonomy = s["error_taxonomy"]
        err_str = f"D:{taxonomy['Address Drift']} L:{taxonomy['Layout Confusion']} C:{taxonomy['Context Bleed']}"
        print(f"  {s['config_name']:<30s} "
              f"{s['pass_rate']*100:>6.1f}% "
              f"{s['extraction_validity_rate']*100:>6.1f}% "
              f"{s['pass_at_k']*100:>6.1f}% "
              f"{s['cove_recovery_rate']*100:>6.1f}% "
              f"{err_str:>10s}")

    if "comparison" in report and report["comparison"]:
        print(f"\n  Relative Gains:")
        for key, gains in report["comparison"].items():
            print(f"    {key}: pass_rate Δ{gains['pass_rate_delta']:+.1%}, "
                  f"validity Δ{gains['extraction_validity_delta']:+.1%}, "
                  f"pass@k Δ{gains['pass_at_k_delta']:+.1%}")

    print(f"\n  Report: {report_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="KarcinoJen Experiment Runner")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument(
        "--config",
        choices=["vanilla", "no_cove", "full", "all"],
        default="all",
        help="Which configuration(s) to run",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"Benchmark file not found: {args.benchmark}")
        print("Run 'python scripts/generate_mcu_bench.py' first.")
        sys.exit(1)

    configs_to_run = None
    if args.config != "all":
        config_map = {
            "vanilla": "vanilla_vlm",
            "no_cove": "karcinojen_no_cove",
            "full": "full_karcinojen",
        }
        configs_to_run = [config_map[args.config]]

    run_experiment(
        benchmark_path=args.benchmark,
        outdir=args.outdir,
        configs_to_run=configs_to_run,
    )


if __name__ == "__main__":
    main()
