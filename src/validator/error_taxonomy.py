"""Qualitative error taxonomy helpers for Package B evidence."""

from __future__ import annotations

from typing import Any


def classify_failure(checks: dict[str, dict[str, Any]]) -> str:
    address = checks.get("address_range", {})
    bit = checks.get("bit_arithmetic", {})
    name = checks.get("name_fuzzy", {})

    if name and not name.get("ok", True):
        return "Context Bleed"

    if address and not address.get("ok", True):
        return "Address Drift"

    if bit and not bit.get("ok", True):
        return "Layout Confusion"

    return "Uncategorized"
