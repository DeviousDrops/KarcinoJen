"""Stage 5 extraction orchestration using prompt_bank + VLM client + schema harness."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from src.extractor.model_config import ExtractionConfig
from src.extractor.prompt_bank import COVE_PROMPT_TEMPLATE, PROMPT_V2
from src.extractor.schema_harness import validate_register_extraction
from src.extractor.vlm_client import VLMClient
from src.validator.svd_validator import RegisterDef, ValidationResult, validate_extraction


@dataclass(frozen=True)
class ExtractionAttempt:
    attempt: int
    schema_valid: bool
    schema_errors: list[str]
    validation_status: str | None
    validation_checks: dict[str, Any] | None
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
    fallback_clients: list[VLMClient] | None = None,
    extraction_cfg: ExtractionConfig,
    query: str,
    page_context: list[dict[str, Any]],
    registers: dict[str, RegisterDef] | None = None,
) -> Stage5Result:
    attempts: list[ExtractionAttempt] = []
    mismatch_report: dict[str, Any] | None = None

    text_only_page_context = [
        {
            "page_id": page.get("page_id"),
            "source_file": page.get("source_file"),
            "page_number": page.get("page_number"),
            "peripheral": page.get("peripheral"),
            "keywords": page.get("keywords", []),
            "page_text": str(page.get("page_text", ""))[:4000],
            "image_path": None,
        }
        for page in page_context
    ]

    for attempt in range(1, extraction_cfg.max_attempts + 1):
        prompt_text = PROMPT_V2 if mismatch_report is None else COVE_PROMPT_TEMPLATE.format(
            mismatch_report=json.dumps(mismatch_report, indent=2)
        )

        try:
            response = client.extract(
                prompt_text=prompt_text,
                query=query,
                page_context=page_context,
                mismatch_report=mismatch_report,
            )
        except Exception as exc:
            attempts.append(
                ExtractionAttempt(
                    attempt=attempt,
                    schema_valid=False,
                    schema_errors=[str(exc)],
                    validation_status=None,
                    validation_checks=None,
                    raw_text="",
                    parsed_json={},
                )
            )
            mismatch_report = {
                "reason": "primary client failed",
                "errors": [str(exc)],
            }
            continue

        schema_result = validate_register_extraction(response.parsed_json)

        validation_status: str | None = None
        validation_checks: dict[str, Any] | None = None
        if schema_result.is_valid and registers is not None:
            validation_result: ValidationResult = validate_extraction(response.parsed_json, registers)
            validation_status = validation_result.status
            validation_checks = validation_result.checks

        attempts.append(
            ExtractionAttempt(
                attempt=attempt,
                schema_valid=schema_result.is_valid,
                schema_errors=schema_result.errors,
                validation_status=validation_status,
                validation_checks=validation_checks,
                raw_text=response.raw_text,
                parsed_json=response.parsed_json,
            )
        )
        if schema_result.is_valid and (registers is None or validation_status == "PASS"):
            return Stage5Result(status="PASS", extraction=response.parsed_json, attempts=attempts)

        if schema_result.is_valid:
            mismatch_report = {
                "reason": "register validation failed",
                "validation_status": validation_status,
                "checks": validation_checks,
            }
        else:
            mismatch_report = {
                "reason": "schema validation failed",
                "errors": schema_result.errors,
            }

    if fallback_clients:
        prompt_text = PROMPT_V2 if mismatch_report is None else COVE_PROMPT_TEMPLATE.format(
            mismatch_report=json.dumps(mismatch_report, indent=2)
        )

        for index, fallback_client in enumerate(fallback_clients, start=1):
            if fallback_client.provider.name == client.provider.name:
                continue

            try:
                response = fallback_client.extract(
                    prompt_text=prompt_text,
                    query=query,
                    page_context=text_only_page_context,
                    mismatch_report=mismatch_report,
                )
            except Exception as exc:
                attempts.append(
                    ExtractionAttempt(
                        attempt=extraction_cfg.max_attempts + index,
                        schema_valid=False,
                        schema_errors=[str(exc)],
                        validation_status=None,
                        validation_checks=None,
                        raw_text="",
                        parsed_json={},
                    )
                )
                continue

            schema_result = validate_register_extraction(response.parsed_json)

            validation_status = None
            validation_checks = None
            if schema_result.is_valid and registers is not None:
                validation_result = validate_extraction(response.parsed_json, registers)
                validation_status = validation_result.status
                validation_checks = validation_result.checks

            attempts.append(
                ExtractionAttempt(
                    attempt=extraction_cfg.max_attempts + index,
                    schema_valid=schema_result.is_valid,
                    schema_errors=schema_result.errors,
                    validation_status=validation_status,
                    validation_checks=validation_checks,
                    raw_text=response.raw_text,
                    parsed_json=response.parsed_json,
                )
            )

            if schema_result.is_valid and (registers is None or validation_status == "PASS"):
                return Stage5Result(status="PASS", extraction=response.parsed_json, attempts=attempts)

    return Stage5Result(status="UNCERTAIN", extraction=None, attempts=attempts)
