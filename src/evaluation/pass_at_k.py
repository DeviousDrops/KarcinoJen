"""PASS@K evaluation and metrics for KarcinoJen Stage 9.

Computes:
- PASS@K: fraction of generated addresses in driver.h that exactly match SVD ground truth
- Extraction validity rate: fraction of extractions that pass schema validation
- CoVe recovery rate: fraction of initial failures recovered by the CoVe loop
- Error taxonomy counts: Address Drift, Layout Confusion, Context Bleed
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.validator.svd_validator import load_svd_registers


@dataclass
class BenchmarkResult:
    """Result of running one benchmark query through a pipeline configuration."""
    query_id: str
    query: str
    config_name: str
    extraction_status: str  # PASS, FAIL, UNCERTAIN
    extraction_attempts: int
    schema_valid: bool
    svd_checks: dict[str, Any] | None
    address_correct: bool
    bit_fields_correct: bool
    name_correct: bool
    timing_valid: bool | None
    error_category: str | None  # Address Drift, Layout Confusion, Context Bleed
    cove_recovered: bool  # True if first attempt failed but final passed
    elapsed_s: float
    extracted_json: dict[str, Any] | None
    ground_truth: dict[str, Any] | None
    pass_k_accuracy: float | None = None


@dataclass
class ConfigResults:
    """Aggregated results for one pipeline configuration."""
    config_name: str
    results: list[BenchmarkResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.extraction_status == "PASS")

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total if self.total else 0.0

    @property
    def extraction_validity_rate(self) -> float:
        if not self.total:
            return 0.0
        return sum(1 for r in self.results if r.schema_valid) / self.total

    @property
    def address_accuracy(self) -> float:
        evaluated = [r for r in self.results if r.extracted_json is not None]
        if not evaluated:
            return 0.0
        return sum(1 for r in evaluated if r.address_correct) / len(evaluated)

    @property
    def cove_recovery_rate(self) -> float:
        recoverable = [r for r in self.results if r.extraction_attempts > 1]
        if not recoverable:
            return 0.0
        return sum(1 for r in recoverable if r.cove_recovered) / len(recoverable)

    @property
    def pass_at_k(self) -> float:
        scored = [r.pass_k_accuracy for r in self.results if r.pass_k_accuracy is not None]
        if not scored:
            return 0.0
        return sum(scored) / len(scored)

    @property
    def error_taxonomy(self) -> dict[str, int]:
        counts: dict[str, int] = {
            "Address Drift": 0,
            "Layout Confusion": 0,
            "Context Bleed": 0,
            "Uncategorized": 0,
        }
        for r in self.results:
            if r.error_category and r.error_category in counts:
                counts[r.error_category] += 1
        return counts

    def summary_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "total_queries": self.total,
            "pass_count": self.pass_count,
            "pass_rate": round(self.pass_rate, 4),
            "extraction_validity_rate": round(self.extraction_validity_rate, 4),
            "pass_at_k": round(self.pass_at_k, 4),
            "address_accuracy": round(self.address_accuracy, 4),
            "cove_recovery_rate": round(self.cove_recovery_rate, 4),
            "error_taxonomy": self.error_taxonomy,
        }


# ── PASS@K: driver.h address verification ────────────────────────────────────

_ADDR_DEFINE_RE = re.compile(
    r"^\s*#define\s+([A-Za-z0-9_]*_ADDR)\s+\(?\s*(0x[0-9A-Fa-f]+)\s*(?:U|UL|ULL)?\s*\)?"
)


def parse_driver_h_addresses(driver_h_path: str | Path) -> dict[str, int]:
    """Parse all address #defines from a generated driver.h file.

    Returns dict mapping macro name to integer address value.
    """
    addresses: dict[str, int] = {}
    path = Path(driver_h_path)
    if not path.exists():
        return addresses

    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ADDR_DEFINE_RE.search(line)
        if match:
            macro_name = match.group(1)
            hex_value = match.group(2)
            addresses[macro_name] = int(hex_value, 16)

    return addresses


def compute_pass_at_k(
    driver_h_path: str | Path,
    svd_path: str | Path,
    *,
    peripheral_filter: str | None = None,
) -> dict[str, Any]:
    """Compute PASS@K by diffing driver.h addresses against SVD ground truth.

    Returns:
        dict with total_defines, matched, mismatched, accuracy, and per-define details.
    """
    generated = parse_driver_h_addresses(driver_h_path)
    registers = load_svd_registers(str(svd_path))

    # Build SVD address lookup: register_key → absolute_address
    svd_addresses: dict[str, int] = {}
    for key, reg_def in registers.items():
        if peripheral_filter and not key.upper().startswith(peripheral_filter.upper()):
            continue
        svd_addresses[key] = reg_def.absolute_address

    results: list[dict[str, Any]] = []
    matched = 0
    mismatched = 0

    for macro_name, generated_addr in generated.items():
        # Try to find matching SVD register
        best_match = None
        for svd_key, svd_addr in svd_addresses.items():
            if generated_addr == svd_addr:
                best_match = {"svd_key": svd_key, "svd_addr": svd_addr, "match": True}
                matched += 1
                break

        if best_match is None:
            mismatched += 1
            # Find closest SVD address for error reporting
            closest_key = ""
            closest_delta = float("inf")
            for svd_key, svd_addr in svd_addresses.items():
                delta = abs(generated_addr - svd_addr)
                if delta < closest_delta:
                    closest_delta = delta
                    closest_key = svd_key

            best_match = {
                "svd_key": closest_key,
                "svd_addr": svd_addresses.get(closest_key),
                "match": False,
                "delta": closest_delta,
            }

        results.append({
            "macro": macro_name,
            "generated_addr": f"0x{generated_addr:08X}",
            **best_match,
        })

    total = matched + mismatched
    accuracy = matched / total if total else 0.0

    return {
        "total_defines": total,
        "matched": matched,
        "mismatched": mismatched,
        "accuracy": round(accuracy, 4),
        "details": results,
    }


def evaluate_extraction_against_ground_truth(
    extraction: dict[str, Any],
    ground_truth: dict[str, Any],
) -> dict[str, bool]:
    """Compare extraction JSON against ground truth JSON.

    Checks address, register name, and bit fields.
    """
    result: dict[str, bool] = {}

    # Address check
    try:
        ext_addr = int(str(extraction.get("base_address", "0x0")), 16) + \
                   int(str(extraction.get("offset", "0x0")), 16)
        gt_addr = int(str(ground_truth.get("base_address", "0x0")), 16) + \
                  int(str(ground_truth.get("offset", "0x0")), 16)
        result["address_correct"] = ext_addr == gt_addr
    except ValueError:
        result["address_correct"] = False

    # Name check
    ext_name = str(extraction.get("register_name", "")).upper()
    gt_name = str(ground_truth.get("register_name", "")).upper()
    result["name_correct"] = ext_name == gt_name

    # Bit fields check — verify at least the core fields match
    ext_bits = extraction.get("bits", [])
    gt_bits = ground_truth.get("bits", [])

    if isinstance(ext_bits, list) and isinstance(gt_bits, list):
        gt_bit_map = {b["name"]: b for b in gt_bits if isinstance(b, dict) and "name" in b}
        ext_bit_map = {b["name"]: b for b in ext_bits if isinstance(b, dict) and "name" in b}

        matching_bits = 0
        total_gt_bits = len(gt_bit_map)

        for name, gt_bit in gt_bit_map.items():
            ext_bit = ext_bit_map.get(name)
            if ext_bit and ext_bit.get("position") == gt_bit.get("position") and \
               ext_bit.get("width") == gt_bit.get("width"):
                matching_bits += 1

        result["bit_fields_correct"] = (
            total_gt_bits > 0 and matching_bits == total_gt_bits
        )
    else:
        result["bit_fields_correct"] = False

    return result


def generate_experiment_report(
    config_results: list[ConfigResults],
) -> dict[str, Any]:
    """Generate a comparative report across all configurations."""
    report = {
        "configurations": [],
        "comparison": {},
    }

    for cfg in config_results:
        report["configurations"].append(cfg.summary_dict())

    # Compute relative gains if we have baseline and full
    if len(config_results) >= 2:
        baseline = config_results[0]
        for other in config_results[1:]:
            key = f"{other.config_name}_vs_{baseline.config_name}"
            report["comparison"][key] = {
                "pass_rate_delta": round(other.pass_rate - baseline.pass_rate, 4),
                "extraction_validity_delta": round(
                    other.extraction_validity_rate - baseline.extraction_validity_rate,
                    4,
                ),
                "pass_at_k_delta": round(other.pass_at_k - baseline.pass_at_k, 4),
                "address_accuracy_delta": round(
                    other.address_accuracy - baseline.address_accuracy, 4
                ),
            }

    return report
