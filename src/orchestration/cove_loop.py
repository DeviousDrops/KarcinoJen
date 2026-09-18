"""Deterministic CoVe correction loop with VLM re-prompt and max-3 retry cap.

Architecture Stage 7: On validation failure, inject the mismatch report back
to the VLM extractor as explicit correction context, retry up to 3 times.
Falls back to deterministic patching if no VLM client is provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy
import json
import logging

from src.validator.svd_validator import RegisterDef, ValidationResult, validate_extraction

logger = logging.getLogger(__name__)


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
    """Apply deterministic corrections based on SVD validation results."""
    corrected = copy.deepcopy(extraction)
    checks = validation.checks
    name_check = checks.get("name_fuzzy", {})
    peripheral_match = bool(name_check.get("peripheral_match", True))

    address_check = checks.get("address_range", {})
    if address_check and not address_check.get("ok", True) and peripheral_match:
        corrected["base_address"] = address_check.get("expected_base_address", corrected.get("base_address"))
        corrected["offset"] = address_check.get("expected_offset", corrected.get("offset"))

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


def _build_mismatch_report(validation: ValidationResult) -> dict[str, Any]:
    """Build a machine-readable mismatch report for VLM re-prompt."""
    failed_checks = {
        name: details
        for name, details in validation.checks.items()
        if not bool(details.get("ok"))
    }
    return {
        "status": validation.status,
        "checks": failed_checks,
        "message": validation.message,
    }


def _pages_for_attempt(
    pages: list[dict[str, Any]],
    *,
    provider_name: str,
    attempt: int,
) -> list[dict[str, Any]]:
    if provider_name != "gemini" or len(pages) <= 1:
        return pages

    page_index = (attempt - 1) % len(pages)
    return [pages[page_index]]


def run_cove_loop(
    initial_extraction: dict[str, Any],
    registers: dict[str, RegisterDef],
    *,
    max_attempts: int = 3,
    vlm_client: Any | None = None,
    fallback_clients: list[Any] | None = None,
    query: str = "",
    page_context: list[dict[str, Any]] | None = None,
) -> CoVeOutcome:
    """Run the CoVe correction loop with VLM re-prompt and deterministic fallback.

    Architecture Stage 7:
    - On validation failure, inject mismatch report back to VLM as correction context
    - If VLM re-prompt fails or no VLM client provided, apply deterministic correction
    - Max 3 iterations, then emit UNCERTAIN

    Args:
        initial_extraction: The initial extraction JSON to validate and correct
        registers: SVD register definitions for validation
        max_attempts: Maximum retry iterations (must be 3 per architecture)
        vlm_client: Optional VLMClient for re-extraction with mismatch context
        query: Original query string (needed for VLM re-prompt)
        page_context: Retrieved page context (needed for VLM re-prompt)
    """
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

        match_key = validation.checks.get("name_fuzzy", {}).get("match_key")
        if not match_key or match_key not in registers:
            break

        # ── VLM re-prompt path (Stage 7 architecture) ────────────────────
        if vlm_client is not None and query and page_context:
            mismatch_report = _build_mismatch_report(validation)
            from src.extractor.prompt_bank import COVE_PROMPT_TEMPLATE
            cove_prompt = COVE_PROMPT_TEMPLATE.format(
                mismatch_report=json.dumps(mismatch_report, indent=2)
            )

            candidates: list[Any] = [vlm_client]
            if fallback_clients:
                for candidate in fallback_clients:
                    if candidate is vlm_client:
                        continue
                    candidates.append(candidate)

            vlm_succeeded = False
            for candidate in candidates:
                provider_name = getattr(getattr(candidate, "provider", None), "name", "unknown")
                logger.info(
                    "CoVe attempt %d: VLM re-prompt via %s [%s]",
                    attempt,
                    provider_name,
                    validation.message,
                )
                candidate_page_context = _pages_for_attempt(
                    page_context,
                    provider_name=provider_name,
                    attempt=attempt,
                )
                try:
                    response = candidate.extract(
                        prompt_text=cove_prompt,
                        query=query,
                        page_context=candidate_page_context,
                        mismatch_report=mismatch_report,
                    )

                    if response.parsed_json and isinstance(response.parsed_json, dict):
                        current = response.parsed_json
                        vlm_succeeded = True
                        logger.info(
                            "CoVe attempt %d: corrected extraction accepted from %s",
                            attempt,
                            provider_name,
                        )
                        break
                except Exception as exc:
                    logger.warning(
                        "CoVe attempt %d: %s re-prompt failed (%s)",
                        attempt,
                        provider_name,
                        exc,
                    )

            if vlm_succeeded:
                continue

        # ── Deterministic fallback ───────────────────────────────────────
        logger.info("CoVe attempt %d: applying deterministic correction", attempt)
        current = apply_deterministic_correction(current, validation, registers[match_key])

    return CoVeOutcome(status="UNCERTAIN", final_extraction=current, attempts=attempts)
