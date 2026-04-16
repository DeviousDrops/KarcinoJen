"""Deterministic CoVe correction loop with max-3 retry cap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy

from src.validator.svd_validator import RegisterDef, ValidationResult, validate_extraction


@dataclass(frozen=True)
class CoVeOutcome:
    status: str
    final_extraction: dict[str, Any]
    attempts: list[dict[str, Any]]


def _clip_bits_to_register(bits: list[dict[str, Any]], register_size: int) -> list[dict[str, Any]]:
    seen_positions: set[int] = set()
    corrected: list[dict[str, Any]] = []

    for bit in bits:
        if not isinstance(bit, dict):
            continue

        position = bit.get("position")
        width = bit.get("width")
        if not isinstance(position, int) or not isinstance(width, int):
            continue

        if position < 0 or width < 1 or position + width > register_size:
            continue

        overlap = any(pos in seen_positions for pos in range(position, position + width))
        if overlap:
            continue

        for pos in range(position, position + width):
            seen_positions.add(pos)

        corrected.append(bit)

    return corrected


def apply_deterministic_correction(
    extraction: dict[str, Any],
    validation: ValidationResult,
    matched_register: RegisterDef,
) -> dict[str, Any]:
    corrected = copy.deepcopy(extraction)
    checks = validation.checks

    address_check = checks.get("address_range", {})
    if address_check and not address_check.get("ok", True):
        corrected["base_address"] = address_check.get("expected_base_address", corrected.get("base_address"))
        corrected["offset"] = address_check.get("expected_offset", corrected.get("offset"))

    name_check = checks.get("name_fuzzy", {})
    if name_check and not name_check.get("ok", True):
        corrected["register_name"] = name_check.get("expected", corrected.get("register_name"))

    bit_check = checks.get("bit_arithmetic", {})
    if bit_check and not bit_check.get("ok", True):
        bits = corrected.get("bits", [])
        if isinstance(bits, list):
            corrected["bits"] = _clip_bits_to_register(bits, matched_register.size)

    timing_check = checks.get("timing_consistency", {})
    if timing_check and not timing_check.get("ok", True):
        constraints = corrected.get("timing_constraints")
        if isinstance(constraints, list):
            for item in constraints:
                if not isinstance(item, dict):
                    continue
                min_v = item.get("min")
                typ_v = item.get("typ")
                max_v = item.get("max")
                numeric = [value for value in (min_v, typ_v, max_v) if isinstance(value, (int, float))]
                if not numeric:
                    continue
                low = min(numeric)
                high = max(numeric)
                item["min"] = low if min_v is not None else None
                item["max"] = high if max_v is not None else None
                if typ_v is not None:
                    item["typ"] = (low + high) / 2.0

    return corrected


def run_cove_loop(
    initial_extraction: dict[str, Any],
    registers: dict[str, RegisterDef],
    *,
    max_attempts: int = 3,
) -> CoVeOutcome:
    if max_attempts != 3:
        raise ValueError("Package B hard constraint: max_attempts must be exactly 3")

    attempts: list[dict[str, Any]] = []
    current = copy.deepcopy(initial_extraction)

    for attempt in range(1, max_attempts + 1):
        validation = validate_extraction(current, registers)
        attempts.append(
            {
                "attempt": attempt,
                "input": copy.deepcopy(current),
                "validation": {
                    "status": validation.status,
                    "checks": validation.checks,
                    "message": validation.message,
                },
            }
        )

        if validation.status == "PASS":
            return CoVeOutcome(status="PASS", final_extraction=current, attempts=attempts)

        expected_name = validation.checks.get("name_fuzzy", {}).get("expected")
        if not expected_name or expected_name not in registers:
            break

        current = apply_deterministic_correction(current, validation, registers[expected_name])

    return CoVeOutcome(status="UNCERTAIN", final_extraction=current, attempts=attempts)
