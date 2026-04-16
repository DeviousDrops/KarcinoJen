"""Deterministic SVD-grounded validator for extracted register JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import xml.etree.ElementTree as ET


def _parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text, 0)


@dataclass(frozen=True)
class RegisterDef:
    name: str
    peripheral: str
    base_address: int
    offset: int
    size: int

    @property
    def absolute_address(self) -> int:
        return self.base_address + self.offset


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    checks: dict[str, dict[str, Any]]
    message: str


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            insertions = previous[j] + 1
            deletions = current[j - 1] + 1
            substitutions = previous[j - 1] + (0 if char_a == char_b else 1)
            current.append(min(insertions, deletions, substitutions))
        previous = current

    return previous[-1]


def load_svd_registers(svd_path: str) -> dict[str, RegisterDef]:
    tree = ET.parse(svd_path)
    root = tree.getroot()

    register_map: dict[str, RegisterDef] = {}

    for peripheral in root.findall(".//peripheral"):
        peripheral_name = peripheral.findtext("name", default="")
        base_address_text = peripheral.findtext("baseAddress", default="0x0")
        base_address = _parse_int(base_address_text)

        for register in peripheral.findall(".//register"):
            register_name = register.findtext("name", default="")
            offset_text = register.findtext("addressOffset", default="0x0")
            size_text = register.findtext("size", default="32")

            register_key = f"{peripheral_name}.{register_name}"
            register_map[register_key] = RegisterDef(
                name=register_name,
                peripheral=peripheral_name,
                base_address=base_address,
                offset=_parse_int(offset_text),
                size=_parse_int(size_text),
            )

    return register_map


def _best_register_match(
    extracted_register_name: str,
    extracted_peripheral: str,
    extracted_address: int | None,
    registers: dict[str, RegisterDef],
) -> tuple[str, RegisterDef, int]:

    best_key = ""
    best_reg: RegisterDef | None = None
    best_score = (10**9, 10**18, 10**9)

    extracted_peripheral_upper = extracted_peripheral.upper()

    for candidate_key, candidate_reg in registers.items():
        distance = _levenshtein_distance(extracted_register_name, candidate_reg.name)
        peripheral_penalty = 0 if candidate_reg.peripheral.upper() == extracted_peripheral_upper else 1
        if extracted_address is None:
            address_delta = 10**18
        else:
            address_delta = abs(candidate_reg.absolute_address - extracted_address)
        score = (distance, address_delta, peripheral_penalty)
        if score < best_score:
            best_key = candidate_key
            best_reg = candidate_reg
            best_score = score

    if best_reg is None:
        raise ValueError("SVD register map is empty")

    return best_key, best_reg, best_score[0]


def _normalize_timing_value(value: float, unit: str) -> float:
    unit_l = unit.strip().lower()
    factors = {
        "s": 1.0,
        "ms": 1e-3,
        "us": 1e-6,
        "ns": 1e-9,
        "ps": 1e-12,
        "hz": 1.0,
        "khz": 1e3,
        "mhz": 1e6,
        "ghz": 1e9,
    }
    if unit_l not in factors:
        raise ValueError(f"Unsupported timing unit: {unit}")
    return value * factors[unit_l]


def _validate_timing_consistency(extraction: dict[str, Any]) -> CheckResult:
    constraints = extraction.get("timing_constraints")
    if constraints is None:
        return CheckResult(True, {"ok": True, "reason": "timing constraints missing (optional)"})

    if not isinstance(constraints, list):
        return CheckResult(False, {"ok": False, "reason": "timing_constraints must be an array"})

    for index, item in enumerate(constraints):
        if not isinstance(item, dict):
            return CheckResult(False, {"ok": False, "reason": f"timing_constraints[{index}] is not an object"})

        unit = item.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            return CheckResult(False, {"ok": False, "reason": f"timing_constraints[{index}] missing unit"})

        present_values: dict[str, float] = {}
        for key in ("min", "typ", "max"):
            value = item.get(key)
            if value is not None:
                if not isinstance(value, (int, float)):
                    return CheckResult(
                        False,
                        {"ok": False, "reason": f"timing_constraints[{index}].{key} must be numeric or null"},
                    )
                present_values[key] = _normalize_timing_value(float(value), unit)

        if "min" in present_values and "typ" in present_values and present_values["min"] > present_values["typ"]:
            return CheckResult(False, {"ok": False, "reason": f"min greater than typ in timing_constraints[{index}]"})

        if "typ" in present_values and "max" in present_values and present_values["typ"] > present_values["max"]:
            return CheckResult(False, {"ok": False, "reason": f"typ greater than max in timing_constraints[{index}]"})

        if "min" in present_values and "max" in present_values and present_values["min"] > present_values["max"]:
            return CheckResult(False, {"ok": False, "reason": f"min greater than max in timing_constraints[{index}]"})

    return CheckResult(True, {"ok": True})


def validate_extraction(
    extraction: dict[str, Any], registers: dict[str, RegisterDef], *, name_distance_limit: int = 2
) -> ValidationResult:
    extracted_name = str(extraction.get("register_name", ""))
    extracted_peripheral = str(extraction.get("peripheral", ""))
    extracted_address: int | None = None
    try:
        extracted_address = int(str(extraction.get("base_address", "0x0")), 16) + int(
            str(extraction.get("offset", "0x0")), 16
        )
    except ValueError:
        extracted_address = None
    best_key, best_register, distance = _best_register_match(
        extracted_name,
        extracted_peripheral,
        extracted_address,
        registers,
    )

    checks: dict[str, dict[str, Any]] = {}

    peripheral_match = (
        not extracted_peripheral
        or best_register.peripheral.upper() == extracted_peripheral.upper()
    )
    name_ok = distance <= name_distance_limit and peripheral_match
    checks["name_fuzzy"] = {
        "ok": name_ok,
        "expected": best_register.name,
        "expected_peripheral": best_register.peripheral,
        "actual": extracted_name,
        "actual_peripheral": extracted_peripheral,
        "match_key": best_key,
        "peripheral_match": peripheral_match,
        "distance": distance,
        "threshold": name_distance_limit,
    }

    try:
        base_address = int(str(extraction.get("base_address", "0x0")), 16)
        offset = int(str(extraction.get("offset", "0x0")), 16)
        resolved_address = base_address + offset
        expected_address = best_register.absolute_address
        address_ok = resolved_address == expected_address
        checks["address_range"] = {
            "ok": address_ok,
            "expected": f"0x{expected_address:08X}",
            "actual": f"0x{resolved_address:08X}",
            "expected_base_address": f"0x{best_register.base_address:08X}",
            "expected_offset": f"0x{best_register.offset:02X}",
            "peripheral": best_register.peripheral,
        }
    except ValueError:
        checks["address_range"] = {
            "ok": False,
            "reason": "base_address or offset is not a valid hex string",
        }

    bits = extraction.get("bits", [])
    seen_positions: set[int] = set()
    arithmetic_ok = True
    arithmetic_reasons: list[str] = []

    if not isinstance(bits, list):
        arithmetic_ok = False
        arithmetic_reasons.append("bits is not an array")
    else:
        for idx, bit in enumerate(bits):
            if not isinstance(bit, dict):
                arithmetic_ok = False
                arithmetic_reasons.append(f"bits[{idx}] is not an object")
                continue

            position = bit.get("position")
            width = bit.get("width")
            if not isinstance(position, int) or not isinstance(width, int):
                arithmetic_ok = False
                arithmetic_reasons.append(f"bits[{idx}] has non-integer position or width")
                continue

            if position + width > best_register.size:
                arithmetic_ok = False
                arithmetic_reasons.append(
                    f"bits[{idx}] exceeds register size {best_register.size}"
                )

            for current_position in range(position, position + width):
                if current_position in seen_positions:
                    arithmetic_ok = False
                    arithmetic_reasons.append(
                        f"bits[{idx}] overlaps at bit position {current_position}"
                    )
                seen_positions.add(current_position)

    checks["bit_arithmetic"] = {
        "ok": arithmetic_ok,
        "register_size": best_register.size,
        "reason": "; ".join(arithmetic_reasons) if arithmetic_reasons else "",
    }

    timing_check = _validate_timing_consistency(extraction)
    checks["timing_consistency"] = timing_check.details

    failed_checks = [name for name, details in checks.items() if not bool(details.get("ok"))]
    status = "PASS" if not failed_checks else "FAIL"
    message = "validation passed" if status == "PASS" else f"failed checks: {', '.join(failed_checks)}"

    return ValidationResult(status=status, checks=checks, message=message)
