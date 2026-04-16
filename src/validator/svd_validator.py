"""Deterministic SVD-grounded validator for extracted register JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import xml.etree.ElementTree as ET


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
        base_address = int(base_address_text, 16)

        for register in peripheral.findall(".//register"):
            register_name = register.findtext("name", default="")
            offset_text = register.findtext("addressOffset", default="0x0")
            size_text = register.findtext("size", default="32")

            register_map[register_name] = RegisterDef(
                name=register_name,
                peripheral=peripheral_name,
                base_address=base_address,
                offset=int(offset_text, 16),
                size=int(size_text),
            )

    return register_map


def _best_register_match(
    extracted_register_name: str, registers: dict[str, RegisterDef]
) -> tuple[str, RegisterDef, int]:
    if extracted_register_name in registers:
        reg = registers[extracted_register_name]
        return reg.name, reg, 0

    best_name = ""
    best_reg: RegisterDef | None = None
    best_distance = 10**9

    for candidate_name, candidate_reg in registers.items():
        distance = _levenshtein_distance(extracted_register_name, candidate_name)
        if distance < best_distance:
            best_name = candidate_name
            best_reg = candidate_reg
            best_distance = distance

    if best_reg is None:
        raise ValueError("SVD register map is empty")

    return best_name, best_reg, best_distance


def _normalize_timing_value(value: float, unit: str) -> float:
    unit_l = unit.strip().lower()
    factors = {
        "s": 1.0,
        "ms": 1e-3,
        "us": 1e-6,
        "ns": 1e-9,
        "ps": 1e-12,
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
    best_name, best_register, distance = _best_register_match(extracted_name, registers)

    checks: dict[str, dict[str, Any]] = {}

    name_ok = distance <= name_distance_limit
    checks["name_fuzzy"] = {
        "ok": name_ok,
        "expected": best_name,
        "actual": extracted_name,
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
