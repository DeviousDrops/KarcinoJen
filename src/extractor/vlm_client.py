"""VLM client wrappers for Gemini, Groq, OpenAI, Ollama, and LLaVA endpoints."""

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
        if self.provider.name == "gemini":
            return self._extract_gemini(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "openai":
            return self._extract_openai_compatible(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "groq":
            return self._extract_openai_compatible(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "ollama":
            return self._extract_ollama(prompt_text, query, page_context, mismatch_report)
        if self.provider.name == "llava":
            return self._extract_llava(prompt_text, query, page_context, mismatch_report)
        raise ValueError(f"Unsupported provider: {self.provider.name}")

    def _extract_gemini(
        self,
        prompt_text: str,
        query: str,
        page_context: list[dict[str, Any]],
        mismatch_report: dict[str, Any] | None,
    ) -> VLMResponse:
        """Extract via Gemini using its OpenAI-compatible endpoint with inline vision.

        Sends up to 3 rendered page images as base64 data-URIs inside the user
        message content array.  Text page context is also included compactly.
        Gemini 2.0 Flash handles both image reading and structured JSON output.
        """
        _load_local_env_files()
        api_key = os.getenv(self.provider.api_key_env or "GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing Gemini API key — set GEMINI_API_KEY in .env or environment."
            )

        # Build compact text context (no image paths — images go inline below).
        compact_pages = [
            {
                "page_id": page.get("page_id"),
                "page_number": page.get("page_number"),
                "page_text": str(page.get("page_text", ""))[:1200],
            }
            for page in page_context
        ]
        text_block = json.dumps(
            {
                "query": query,
                "pages": compact_pages,
                "mismatch_report": mismatch_report,
            },
            indent=2,
        )

        # User message content: text first, then up to 3 page images inline.
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": text_block}
        ]
        images_added = 0
        for page in page_context:
            if images_added >= 3:
                break
            image_path = page.get("image_path")
            if image_path and Path(image_path).exists():
                b64 = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
                images_added += 1

        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": user_content},
        ]

        url_base = self.provider.base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
        endpoint = f"{url_base.rstrip('/')}/chat/completions"
        body: dict[str, Any] = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": 0,
            # Gemini supports response_format json_object via its OpenAI-compat endpoint.
            "response_format": {"type": "json_object"},
        }

        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "KarcinoJen/1.0 (datasheet-driver-generator)",
            },
        )

        try:
            with request.urlopen(req, timeout=self.provider.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini request failed: {exc.code} {details}") from exc

        content = payload["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
        return VLMResponse(raw_text=content, parsed_json=parsed)


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

        # Strip image_path from text-only context to avoid bloating the token payload.
        text_pages = [
            {k: v for k, v in page.items() if k != "image_path"}
            for page in page_context
        ]
        evidence_text = json.dumps(
            {
                "query": query,
                "pages": text_pages,
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
        body: dict[str, Any] = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": 0,
        }
        # json_object response_format is supported by OpenAI but not by all Groq models.
        # Only request it for the openai provider to avoid 400 errors on Groq.
        if self.provider.name == "openai":
            body["response_format"] = {"type": "json_object"}

        req = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "KarcinoJen/1.0 (datasheet-driver-generator)",
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
        # Use OLLAMA_CHAT_ENDPOINT for the chat/text path; OLLAMA_ENDPOINT is for llava/generate.
        endpoint = os.getenv("OLLAMA_CHAT_ENDPOINT") or (
            os.getenv(self.provider.endpoint_env) if self.provider.endpoint_env else None
        )
        if not endpoint:
            endpoint = "http://localhost:11434/api/chat"

        # Strip image_path — Ollama text models don't accept image bytes over the chat API.
        text_pages = [
            {k: v for k, v in page.items() if k != "image_path"}
            for page in page_context
        ]
        evidence_text = json.dumps(
            {
                "query": query,
                "pages": text_pages,
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

        # Collect up to 2 rendered images (base64) from the top pages.
        images_b64: list[str] = []
        for page in page_context:
            if len(images_b64) >= 2:
                break
            image_path = page.get("image_path")
            if image_path and Path(image_path).exists():
                images_b64.append(
                    base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
                )

        # Build a compact text-only context for LLaVA (strip image_path, truncate text).
        compact_pages = [
            {
                "page_id": page.get("page_id"),
                "page_number": page.get("page_number"),
                "page_text": str(page.get("page_text", ""))[:800],
            }
            for page in page_context
        ]

        llava_prompt = (
            f"{prompt_text}\n\n"
            f"QUERY:\n{query}\n\n"
            f"PAGE_TEXT_CONTEXT:\n{json.dumps(compact_pages, indent=2)}\n\n"
            f"MISMATCH_REPORT:\n{json.dumps(mismatch_report, indent=2) if mismatch_report else 'null'}\n"
            "Return only JSON."
        )

        payload: dict[str, Any] = {
            "model": self.provider.model,
            "prompt": llava_prompt,
            "stream": False,
            "format": "json",
        }
        if images_b64:
            payload["images"] = images_b64

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
