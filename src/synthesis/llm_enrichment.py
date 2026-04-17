"""LLM-based driver.c enrichment with provider fallbacks."""

from __future__ import annotations

import json
from pathlib import Path

from src.extractor.vlm_client import VLMClient


def _extract_driver_c_from_response(response) -> str | None:
    parsed = response.parsed_json
    if isinstance(parsed, dict):
        value = parsed.get("driver_c") or parsed.get("code") or parsed.get("content")
        if isinstance(value, str):
            return value.strip()

    raw = str(response.raw_text or "").strip()
    if raw.startswith("#include") and "void " in raw:
        return raw
    return None


def enrich_driver_with_fallback(
    *,
    validated_payload: dict[str, object],
    driver_h_path: Path,
    driver_c_path: Path,
    clients: list[VLMClient],
) -> tuple[bool, str]:
    """Try to enrich driver.c with one of the supplied clients.

    Returns:
        (ok, provider_name_or_reason)
    """
    if not driver_h_path.exists() or not driver_c_path.exists():
        return False, "missing_driver_files"

    if not clients:
        return False, "no_llm_clients"

    template_c = driver_c_path.read_text(encoding="utf-8")
    template_h = driver_h_path.read_text(encoding="utf-8")

    prompt = (
        "You are an embedded C code assistant.\n"
        "Improve the provided template driver.c while preserving register defines from driver.h.\n"
        "Return ONLY valid JSON with this schema:"
        '{"driver_c":"<full compilable C source code>"}.\n'
        "Rules:\n"
        "1) Keep #include \"driver.h\"\n"
        "2) Keep function signatures unchanged\n"
        "3) Implement function bodies with sensible register operations\n"
        "4) Do not add markdown fences\n"
    )

    evidence = json.dumps(
        {
            "validated_extraction": validated_payload,
            "template_driver_h": template_h,
            "template_driver_c": template_c,
        },
        indent=2,
    )

    page_context = [
        {
            "page_id": str(validated_payload.get("source_page_id", "extracted")),
            "page_text": evidence,
            "image_path": None,
        }
    ]

    errors: list[str] = []
    for client in clients:
        provider_name = client.provider.name
        try:
            response = client.extract(
                prompt_text=prompt,
                query="Enrich generated driver.c",
                page_context=page_context,
                mismatch_report=None,
            )
            code = _extract_driver_c_from_response(response)
            if code and "#include \"driver.h\"" in code:
                driver_c_path.write_text(code, encoding="utf-8")
                return True, provider_name
            errors.append(f"{provider_name}: invalid_code_payload")
        except Exception as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}: {exc}")

    return False, " | ".join(errors) if errors else "unknown_error"
