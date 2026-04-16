"""Stage 5 extraction orchestration using prompt_bank + VLM client + schema harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.extractor.model_config import ExtractionConfig
from src.extractor.prompt_bank import COVE_PROMPT_TEMPLATE, PROMPT_V2
from src.extractor.schema_harness import validate_register_extraction
from src.extractor.vlm_client import VLMClient


@dataclass(frozen=True)
class ExtractionAttempt:
    attempt: int
    schema_valid: bool
    schema_errors: list[str]
    raw_text: str
    parsed_json: dict[str, Any]


@dataclass(frozen=True)
class Stage5Result:
    status: str
    extraction: dict[str, Any] | None
    attempts: list[ExtractionAttempt]


def run_stage5_extraction(
    *,
    client: VLMClient,
    extraction_cfg: ExtractionConfig,
    query: str,
    page_context: list[dict[str, Any]],
    mismatch_report: dict[str, Any] | None = None,
) -> Stage5Result:
    attempts: list[ExtractionAttempt] = []

    for attempt in range(1, extraction_cfg.max_attempts + 1):
        if mismatch_report:
            prompt_text = COVE_PROMPT_TEMPLATE.format(mismatch_report=mismatch_report)
        else:
            prompt_text = PROMPT_V2

        response = client.extract(
            prompt_text=prompt_text,
            query=query,
            page_context=page_context,
            mismatch_report=mismatch_report,
        )
        schema_result = validate_register_extraction(response.parsed_json)
        attempts.append(
            ExtractionAttempt(
                attempt=attempt,
                schema_valid=schema_result.is_valid,
                schema_errors=schema_result.errors,
                raw_text=response.raw_text,
                parsed_json=response.parsed_json,
            )
        )

        if schema_result.is_valid:
            return Stage5Result(status="PASS", extraction=response.parsed_json, attempts=attempts)

    return Stage5Result(status="FAIL", extraction=None, attempts=attempts)
