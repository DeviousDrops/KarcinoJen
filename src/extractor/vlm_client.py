"""VLM client wrappers for OpenAI, Groq, Ollama, or LLaVA endpoints."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from src.extractor.model_config import ProviderConfig

ROOT = Path(__file__).resolve().parents[2]


def _load_local_env_files() -> None:
    for name in (".env", ".ENV"):
        env_path = ROOT / name
        if not env_path.exists():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass(frozen=True)
class VLMResponse:
    raw_text: str
    parsed_json: dict[str, Any]


class VLMClient:
    def __init__(self, provider: ProviderConfig):
        self.provider = provider

    def extract(
        self,
        *,
        prompt_text: str,
        query: str,
        page_context: list[dict[str, Any]],
        mismatch_report: dict[str, Any] | None = None,
    ) -> VLMResponse:
        if self.provider.name == "openai":
            return self._extract_openai_compatible(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "groq":
            return self._extract_openai_compatible(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "ollama":
            return self._extract_ollama(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "llava":
            return self._extract_llava(prompt_text, query, page_context, mismatch_report)
        raise ValueError(f"Unsupported provider: {self.provider.name}")

    def _extract_openai_compatible(
        self,
        prompt_text: str,
        query: str,
        page_context: list[dict[str, Any]],
        mismatch_report: dict[str, Any] | None,
    ) -> VLMResponse:
        _load_local_env_files()
        if not self.provider.api_key_env:
            raise ValueError(f"{self.provider.name} provider missing api_key_env in config")

        api_key = os.getenv(self.provider.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key in environment variable {self.provider.api_key_env}"
            )

        evidence_text = json.dumps(
            {
                "query": query,
                "pages": page_context,
                "mismatch_report": mismatch_report,
            },
            indent=2,
        )

        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": evidence_text},
        ]

        url_base = self.provider.base_url or "https://api.openai.com/v1"
        endpoint = f"{url_base.rstrip('/')}/chat/completions"
        body = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with request.urlopen(req, timeout=self.provider.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider.name} request failed: {exc.code} {details}") from exc

        content = payload["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
        return VLMResponse(raw_text=content, parsed_json=parsed)

    def _extract_ollama(
        self,
        prompt_text: str,
        query: str,
        page_context: list[dict[str, Any]],
        mismatch_report: dict[str, Any] | None,
    ) -> VLMResponse:
        endpoint = None
        if self.provider.endpoint_env:
            endpoint = os.getenv(self.provider.endpoint_env)
        if not endpoint:
            endpoint = "http://localhost:11434/api/chat"

        evidence_text = json.dumps(
            {
                "query": query,
                "pages": page_context,
                "mismatch_report": mismatch_report,
            },
            indent=2,
        )

        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": evidence_text},
        ]

        body = {
            "model": self.provider.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }

        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.provider.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama request failed: {exc.code} {details}") from exc

        message = payload.get("message") or {}
        content = str(message.get("content", "")).strip()
        parsed = _parse_json_object(content)
        return VLMResponse(raw_text=content, parsed_json=parsed)

    def _extract_llava(
        self,
        prompt_text: str,
        query: str,
        page_context: list[dict[str, Any]],
        mismatch_report: dict[str, Any] | None,
    ) -> VLMResponse:
        endpoint = None
        if self.provider.endpoint_env:
            endpoint = os.getenv(self.provider.endpoint_env)
        if not endpoint:
            endpoint = "http://localhost:11434/api/generate"

        first_image_b64 = None
        for page in page_context:
            image_path = page.get("image_path")
            if image_path and Path(image_path).exists():
                first_image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
                break

        llava_prompt = (
            f"{prompt_text}\n\n"
            f"QUERY:\n{query}\n\n"
            f"PAGE_CONTEXT:\n{json.dumps(page_context, indent=2)}\n\n"
            f"MISMATCH_REPORT:\n{json.dumps(mismatch_report, indent=2) if mismatch_report else 'null'}\n"
            "Return only JSON."
        )

        payload: dict[str, Any] = {
            "model": self.provider.model,
            "prompt": llava_prompt,
            "stream": False,
            "format": "json",
        }
        if first_image_b64:
            payload["images"] = [first_image_b64]

        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.provider.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLaVA request failed: {exc.code} {details}") from exc

        content = str(response_payload.get("response", "")).strip()
        parsed = _parse_json_object(content)
        return VLMResponse(raw_text=content, parsed_json=parsed)

def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start : end + 1]
            return json.loads(candidate)
        raise
