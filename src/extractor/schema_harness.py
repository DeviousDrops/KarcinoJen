"""Schema validation harness for register extraction JSON."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

HEX_PATTERN = re.compile(r"^0x[0-9A-Fa-f]+$")


@dataclass(frozen=True)
class SchemaCheckResult:
    is_valid: bool
    errors: list[str]


def _is_hex_string(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_PATTERN.match(value))


def _validate_timing_constraint(item: Any, index: int, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"timing_constraints[{index}] must be an object")
        return

    required = {"name", "unit"}
    allowed = {"name", "min", "typ", "max", "unit", "condition", "source_page"}

    missing = required - item.keys()
    if missing:
        errors.append(
            f"timing_constraints[{index}] missing required keys: {sorted(missing)}"
        )

    extra = set(item.keys()) - allowed
    if extra:
        errors.append(f"timing_constraints[{index}] has unexpected keys: {sorted(extra)}")

    if "name" in item and (not isinstance(item["name"], str) or not item["name"].strip()):
        errors.append(f"timing_constraints[{index}].name must be a non-empty string")

    if "unit" in item and (not isinstance(item["unit"], str) or not item["unit"].strip()):
        errors.append(f"timing_constraints[{index}].unit must be a non-empty string")

    for numeric_key in ("min", "typ", "max"):
        if numeric_key in item and item[numeric_key] is not None and not isinstance(
            item[numeric_key], (int, float)
        ):
            errors.append(
                f"timing_constraints[{index}].{numeric_key} must be number or null"
            )

    if "source_page" in item and not (
        isinstance(item["source_page"], int) and item["source_page"] >= 1
    ):
        errors.append(f"timing_constraints[{index}].source_page must be integer >= 1")


def validate_register_extraction(payload: Any) -> SchemaCheckResult:
    errors: list[str] = []

    if not isinstance(payload, dict):
        return SchemaCheckResult(False, ["payload must be an object"])

    required = {"peripheral", "register_name", "base_address", "offset", "bits"}
    allowed = required | {"timing_constraints"}

    missing = required - payload.keys()
    if missing:
        errors.append(f"missing required keys: {sorted(missing)}")

    extra = set(payload.keys()) - allowed
    if extra:
        errors.append(f"unexpected keys present: {sorted(extra)}")

    if "peripheral" in payload and (
        not isinstance(payload["peripheral"], str) or not payload["peripheral"].strip()
    ):
        errors.append("peripheral must be a non-empty string")

    if "register_name" in payload and (
        not isinstance(payload["register_name"], str)
        or not payload["register_name"].strip()
    ):
        errors.append("register_name must be a non-empty string")

    if "base_address" in payload and not _is_hex_string(payload["base_address"]):
        errors.append("base_address must match hex pattern like 0x40004400")

    if "offset" in payload and not _is_hex_string(payload["offset"]):
        errors.append("offset must match hex pattern like 0x00")

    bits = payload.get("bits")
    if bits is None or not isinstance(bits, list):
        errors.append("bits must be an array")
    else:
        for idx, item in enumerate(bits):
            if not isinstance(item, dict):
                errors.append(f"bits[{idx}] must be an object")
                continue

            bit_required = {"name", "position", "width", "access"}
            bit_allowed = set(bit_required)

            bit_missing = bit_required - item.keys()
            if bit_missing:
                errors.append(f"bits[{idx}] missing required keys: {sorted(bit_missing)}")

            bit_extra = set(item.keys()) - bit_allowed
            if bit_extra:
                errors.append(f"bits[{idx}] has unexpected keys: {sorted(bit_extra)}")

            if "name" in item and (not isinstance(item["name"], str) or not item["name"].strip()):
                errors.append(f"bits[{idx}].name must be a non-empty string")

            if "position" in item and not (
                isinstance(item["position"], int) and item["position"] >= 0
            ):
                errors.append(f"bits[{idx}].position must be integer >= 0")

            if "width" in item and not (
                isinstance(item["width"], int) and item["width"] >= 1
            ):
                errors.append(f"bits[{idx}].width must be integer >= 1")

            if "access" in item and not isinstance(item["access"], str):
                errors.append(f"bits[{idx}].access must be a string")

    timing_constraints = payload.get("timing_constraints")
    if timing_constraints is not None:
        if not isinstance(timing_constraints, list):
            errors.append("timing_constraints must be an array when present")
        else:
            for idx, item in enumerate(timing_constraints):
                _validate_timing_constraint(item, idx, errors)

    return SchemaCheckResult(is_valid=not errors, errors=errors)
