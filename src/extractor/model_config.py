"""Model and retrieval configuration loader for KarcinoJen."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    model: str
    api_key_env: str | None
    endpoint_env: str | None
    base_url: str | None
    timeout_seconds: int


@dataclass(frozen=True)
class ExtractionConfig:
    temperature: float
    max_attempts: int
    response_format: str


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int
    lexical_weight: float
    semantic_weight: float
    hex_token_boost: float
    rrf_k: int


@dataclass(frozen=True)
class RuntimeConfig:
    version: str
    selected_provider: str
    provider: ProviderConfig
    extraction: ExtractionConfig
    retrieval: RetrievalConfig


def load_runtime_config(config_path: Path) -> RuntimeConfig:
    payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    selected_provider = str(payload["selected_provider"])

    provider_payload = payload["providers"][selected_provider]
    provider = ProviderConfig(
        name=selected_provider,
        model=str(provider_payload["model"]),
        api_key_env=provider_payload.get("api_key_env"),
        endpoint_env=provider_payload.get("endpoint_env"),
        base_url=provider_payload.get("base_url"),
        timeout_seconds=int(provider_payload.get("timeout_seconds", 60)),
    )

    extraction_payload = payload["extraction"]
    extraction = ExtractionConfig(
        temperature=float(extraction_payload.get("temperature", 0)),
        max_attempts=int(extraction_payload.get("max_attempts", 3)),
        response_format=str(extraction_payload.get("response_format", "json_object")),
    )

    retrieval_payload = payload["retrieval"]
    retrieval = RetrievalConfig(
        top_k=int(retrieval_payload.get("top_k", 3)),
        lexical_weight=float(retrieval_payload.get("lexical_weight", 0.55)),
        semantic_weight=float(retrieval_payload.get("semantic_weight", 0.45)),
        hex_token_boost=float(retrieval_payload.get("hex_token_boost", 2.0)),
        rrf_k=int(retrieval_payload.get("rrf_k", 60)),
    )

    return RuntimeConfig(
        version=str(payload.get("version", "1.0")),
        selected_provider=selected_provider,
        provider=provider,
        extraction=extraction,
        retrieval=retrieval,
    )
