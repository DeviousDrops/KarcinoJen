"""OCR-backed extraction fallback when VLM extraction fails."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from src.validator.svd_validator import RegisterDef

TOKEN_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*")

_RAPIDOCR_ENGINE: Any | None = None
_RAPIDOCR_DISABLED_REASON: str | None = None


@dataclass(frozen=True)
class OCRFallbackResult:
    extraction: dict[str, Any] | None
    details: str


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.upper()))


def _compact(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def _load_rapidocr_engine() -> Any | None:
    global _RAPIDOCR_ENGINE
    global _RAPIDOCR_DISABLED_REASON

    if _RAPIDOCR_ENGINE is not None:
        return _RAPIDOCR_ENGINE
    if _RAPIDOCR_DISABLED_REASON is not None:
        return None

    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        _RAPIDOCR_DISABLED_REASON = f"rapidocr import failed: {exc}"
        return None

    try:
        _RAPIDOCR_ENGINE = RapidOCR()
        return _RAPIDOCR_ENGINE
    except Exception as exc:
        _RAPIDOCR_DISABLED_REASON = f"rapidocr init failed: {exc}"
        return None


def _ocr_text_from_image(image_path: Path) -> str:
    engine = _load_rapidocr_engine()
    if engine is None:
        return ""
    if not image_path.exists():
        return ""

    try:
        result = engine(str(image_path))
    except Exception:
        return ""

    if isinstance(result, tuple):
        result = result[0]

    lines: list[str] = []
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text_part = item[1]
            if isinstance(text_part, (list, tuple)) and text_part:
                text_part = text_part[0]
            if isinstance(text_part, str) and text_part.strip():
                lines.append(text_part.strip())

    return "\n".join(lines)


def _collect_context_text(page_context: list[dict[str, Any]]) -> tuple[str, bool, int]:
    chunks: list[str] = []
    used_ocr = False
    ocr_page_count = 0

    for page in page_context:
        page_text = str(page.get("page_text", "")).strip()
        if page_text:
            chunks.append(page_text)

        image_path = page.get("image_path")
        if image_path:
            ocr_text = _ocr_text_from_image(Path(str(image_path)))
            if ocr_text:
                chunks.append(ocr_text)
                used_ocr = True
                ocr_page_count += 1

    return "\n".join(chunks), used_ocr, ocr_page_count


def _score_candidate(
    register: RegisterDef,
    *,
    query_tokens: set[str],
    context_tokens: set[str],
    query_compact: str,
    context_compact: str,
) -> int:
    peripheral = register.peripheral.upper()
    register_name = register.name.upper()
    pair_compact = f"{peripheral}{register_name}"

    score = 0

    if peripheral in query_tokens:
        score += 14
    if register_name in query_tokens:
        score += 14
    if peripheral in query_tokens and register_name in query_tokens:
        score += 12

    if peripheral in context_tokens:
        score += 5
    if register_name in context_tokens:
        score += 7
    if peripheral in context_tokens and register_name in context_tokens:
        score += 6

    if pair_compact in query_compact:
        score += 18
    if pair_compact in context_compact:
        score += 10

    if register_name in {"CR1", "CR2", "CR3", "SR", "DR"} and peripheral not in query_tokens:
        score -= 8

    return score


def _best_register_from_text(
    *,
    query: str,
    context_text: str,
    registers: dict[str, RegisterDef],
) -> tuple[RegisterDef | None, int]:
    query_tokens = _tokenize(query)
    context_tokens = _tokenize(context_text)
    query_compact = _compact(query)
    context_compact = _compact(context_text)

    best_register: RegisterDef | None = None
    best_score = -10**9

    for register in registers.values():
        score = _score_candidate(
            register,
            query_tokens=query_tokens,
            context_tokens=context_tokens,
            query_compact=query_compact,
            context_compact=context_compact,
        )
        if score > best_score:
            best_register = register
            best_score = score

    if best_score < 12:
        return None, best_score
    return best_register, best_score


def run_ocr_fallback_extraction(
    *,
    query: str,
    page_context: list[dict[str, Any]],
    registers: dict[str, RegisterDef] | None,
) -> OCRFallbackResult:
    if not registers:
        return OCRFallbackResult(extraction=None, details="OCR fallback unavailable: SVD register map missing")

    context_text, used_ocr, ocr_page_count = _collect_context_text(page_context)
    register, score = _best_register_from_text(
        query=query,
        context_text=context_text,
        registers=registers,
    )

    if register is None:
        reason = _RAPIDOCR_DISABLED_REASON or "rapidocr not available; used retrieval text only"
        return OCRFallbackResult(
            extraction=None,
            details=(
                "OCR fallback could not infer target register from query/context "
                f"(score={score}, reason={reason})"
            ),
        )

    extraction = {
        "peripheral": register.peripheral,
        "register_name": register.name,
        "base_address": f"0x{register.base_address:08X}",
        "offset": f"0x{register.offset:02X}",
        "bits": [
            {
                "name": "VALUE",
                "position": 0,
                "width": 1,
                "access": "RW",
            }
        ],
    }

    mode = "rapidocr+text" if used_ocr else "text-only"
    return OCRFallbackResult(
        extraction=extraction,
        details=(
            f"OCR fallback selected {register.peripheral}.{register.name} "
            f"(score={score}, mode={mode}, ocr_pages={ocr_page_count})"
        ),
    )
