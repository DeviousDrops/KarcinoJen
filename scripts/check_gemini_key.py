#!/usr/bin/env python3
"""Verify Gemini API key health for KarcinoJen.

This script is designed as a fast preflight check before running the full
pipeline/tests. It verifies whether your key works with:

1) Native Gemini path used by this project pipeline
    - google-genai SDK (Client.models.list and Client.models.generate_content)

2) Gemini OpenAI-compatible endpoint
   - GET /v1beta/openai/models with Authorization: Bearer <key>

It also warns when .env and .ENV contain conflicting key values, because the
project loader reads .env first and only fills missing variables from .ENV.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import load_runtime_config
from src.extractor.vlm_client import _load_local_env_files

DEFAULT_CONFIG_PATH = ROOT / "configs" / "model_config.json"


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    status_code: int | None
    summary: str
    body_head: str


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 12:
        return "*" * len(secret)
    return f"{secret[:8]}...{secret[-4:]}"


def _sanitize_head(text: str, limit: int = 220) -> str:
    cleaned = text.replace("\n", " ").replace("\r", " ").strip()
    return cleaned[:limit]


def _summarize_error_body(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _sanitize_head(body)

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            parts = [
                str(err.get("code")) if err.get("code") is not None else "",
                str(err.get("status") or ""),
                str(err.get("message") or ""),
            ]
            summary = " | ".join(part for part in parts if part)
            return _sanitize_head(summary)

    return _sanitize_head(body)


def _http_json_request(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout_s: int,
) -> ProbeResult:
    data = json.dumps(body).encode("utf-8") if body is not None else None

    req = request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            return ProbeResult(
                name="",
                ok=True,
                status_code=resp.status,
                summary="OK",
                body_head=_sanitize_head(payload),
            )
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return ProbeResult(
            name="",
            ok=False,
            status_code=exc.code,
            summary=_summarize_error_body(payload),
            body_head=_sanitize_head(payload),
        )
    except error.URLError as exc:
        return ProbeResult(
            name="",
            ok=False,
            status_code=None,
            summary=f"NETWORK_ERROR: {exc.reason}",
            body_head="",
        )


def _probe_native_generate(*, model: str, api_key: str, timeout_s: int) -> ProbeResult:
    try:
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types
    except ImportError as exc:
        return ProbeResult(
            name="native_generate",
            ok=False,
            status_code=None,
            summary=f"SDK_MISSING: {exc}",
            body_head="",
        )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_text(
                    text='Return exactly this JSON object and nothing else: {"ok":true}'
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                max_output_tokens=32,
            ),
        )

        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            return ProbeResult(
                name="native_generate",
                ok=False,
                status_code=200,
                summary="EMPTY_RESPONSE",
                body_head="",
            )

        return ProbeResult(
            name="native_generate",
            ok=True,
            status_code=200,
            summary="OK (google-genai SDK)",
            body_head=_sanitize_head(text),
        )
    except genai_errors.APIError as exc:
        status = getattr(exc, "status", "")
        message = getattr(exc, "message", "")
        detail = " | ".join(item for item in [str(status), str(message)] if item)
        if not detail:
            detail = str(exc)
        return ProbeResult(
            name="native_generate",
            ok=False,
            status_code=exc.code,
            summary=f"{exc.code} | {detail}",
            body_head=_sanitize_head(detail),
        )
    except Exception as exc:
        return ProbeResult(
            name="native_generate",
            ok=False,
            status_code=None,
            summary=f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}",
            body_head="",
        )


def _probe_native_models(*, api_key: str, timeout_s: int) -> ProbeResult:
    try:
        from google import genai
        from google.genai import errors as genai_errors
    except ImportError as exc:
        return ProbeResult(
            name="native_models",
            ok=False,
            status_code=None,
            summary=f"SDK_MISSING: {exc}",
            body_head="",
        )

    try:
        client = genai.Client(api_key=api_key)
        first_model = None
        for model in client.models.list():
            first_model = model
            break

        if first_model is None:
            return ProbeResult(
                name="native_models",
                ok=True,
                status_code=200,
                summary="OK (google-genai SDK) | no models returned",
                body_head="",
            )

        model_name = getattr(first_model, "name", "")
        display_name = getattr(first_model, "display_name", "")
        body = json.dumps({"first_model": model_name, "display_name": display_name})

        return ProbeResult(
            name="native_models",
            ok=True,
            status_code=200,
            summary="OK (google-genai SDK)",
            body_head=_sanitize_head(body),
        )
    except genai_errors.APIError as exc:
        status = getattr(exc, "status", "")
        message = getattr(exc, "message", "")
        detail = " | ".join(item for item in [str(status), str(message)] if item)
        if not detail:
            detail = str(exc)
        return ProbeResult(
            name="native_models",
            ok=False,
            status_code=exc.code,
            summary=f"{exc.code} | {detail}",
            body_head=_sanitize_head(detail),
        )
    except Exception as exc:
        return ProbeResult(
            name="native_models",
            ok=False,
            status_code=None,
            summary=f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}",
            body_head="",
        )


def _probe_openai_models(*, api_key: str, timeout_s: int) -> ProbeResult:
    url = "https://generativelanguage.googleapis.com/v1beta/openai/models"
    result = _http_json_request(
        url=url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "KarcinoJen-keycheck/1.0",
        },
        body=None,
        timeout_s=timeout_s,
    )
    return ProbeResult(
        name="openai_models",
        ok=result.ok,
        status_code=result.status_code,
        summary=result.summary,
        body_head=result.body_head,
    )


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, raw = stripped.split("=", 1)
        key = key.strip()
        value = raw.strip().strip('"').strip("'")
        if key:
            values[key] = value

    return values


def _print_env_diagnostics(primary_env_var: str) -> None:
    env_path = ROOT / ".env"
    env_upper_path = ROOT / ".ENV"

    env_values = _parse_env_file(env_path)
    env_upper_values = _parse_env_file(env_upper_path)

    print("Environment file diagnostics:")
    print(f"  - .env exists:  {env_path.exists()}")
    print(f"  - .ENV exists:  {env_upper_path.exists()}")

    keys_to_check = [primary_env_var, "GEMINI_API_KEY", "GOOGLE_API_KEY"]
    seen: set[str] = set()
    for key_name in keys_to_check:
        if key_name in seen:
            continue
        seen.add(key_name)
        left = env_values.get(key_name)
        right = env_upper_values.get(key_name)
        if left and right:
            same = left == right
            print(
                f"  - {key_name}: in both files | .env={_mask_secret(left)} | .ENV={_mask_secret(right)} | same={same}"
            )
            if not same:
                print(
                    "    WARNING: .env and .ENV differ. Loader reads .env first and will keep that value."
                )
        elif left:
            print(f"  - {key_name}: found in .env as {_mask_secret(left)}")
        elif right:
            print(f"  - {key_name}: found in .ENV as {_mask_secret(right)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Gemini API key health")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to model config JSON (default: configs/model_config.json)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model for native generate test (default from config gemini provider)",
    )
    parser.add_argument(
        "--mode",
        choices=["pipeline", "openai", "auto"],
        default="pipeline",
        help="Which auth path to require: pipeline(native), openai, or auto",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (ROOT / config_path).resolve()

    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    runtime_cfg = load_runtime_config(config_path)
    gemini_provider = runtime_cfg.providers.get("gemini")

    primary_env_var = "GEMINI_API_KEY"
    model = "gemini-2.0-flash"

    if gemini_provider is not None:
        if gemini_provider.api_key_env:
            primary_env_var = gemini_provider.api_key_env
        model = gemini_provider.model

    if args.model:
        model = args.model

    _load_local_env_files()

    env_candidates = [primary_env_var, "GEMINI_API_KEY", "GOOGLE_API_KEY"]
    api_key = ""
    key_source = ""
    for candidate in env_candidates:
        value = os.getenv(candidate)
        if value:
            api_key = value.strip()
            key_source = candidate
            break

    if not args.json:
        print("=" * 72)
        print("Gemini Key Health Check")
        print("=" * 72)
        print(f"Config:      {config_path}")
        print(f"Model:       {model}")
        print(f"Mode:        {args.mode}")
        print(f"Primary env: {primary_env_var}")
        _print_env_diagnostics(primary_env_var)

    if not api_key:
        message = "No Gemini key found in env vars: " + ", ".join(env_candidates)
        if args.json:
            print(json.dumps({"ok": False, "error": message}, indent=2))
        raise SystemExit(1)

    native_models_result = _probe_native_models(api_key=api_key, timeout_s=args.timeout)
    native_result = _probe_native_generate(model=model, api_key=api_key, timeout_s=args.timeout)
    openai_result = _probe_openai_models(api_key=api_key, timeout_s=args.timeout)

    quota_limited = native_result.status_code == 429
    auth_valid = native_models_result.ok or quota_limited
    pipeline_ready = native_result.ok

    if args.mode == "pipeline":
        ok = pipeline_ready
    elif args.mode == "openai":
        ok = openai_result.ok
    else:
        ok = auth_valid or openai_result.ok

    if args.json:
        payload = {
            "ok": ok,
            "mode": args.mode,
            "model": model,
            "key_source": key_source,
            "key_preview": _mask_secret(api_key),
            "native_models": asdict(native_models_result),
            "native_generate": asdict(native_result),
            "openai_models": asdict(openai_result),
            "auth_valid": auth_valid,
            "quota_limited": quota_limited,
            "pipeline_ready": pipeline_ready,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"Key source:  {key_source}")
        print(f"Key preview: {_mask_secret(api_key)} (len={len(api_key)})")
        print()
        print("Probe results:")
        print(
            f"  - native_models:   ok={native_models_result.ok} "
            f"status={native_models_result.status_code} summary={native_models_result.summary}"
        )
        print(
            f"  - native_generate: ok={native_result.ok} "
            f"status={native_result.status_code} summary={native_result.summary}"
        )
        print(
            f"  - openai_models:   ok={openai_result.ok} "
            f"status={openai_result.status_code} summary={openai_result.summary}"
        )
        print()

        if pipeline_ready:
            print("Result: PASS for pipeline/native Gemini flow.")
        elif quota_limited and auth_valid:
            print("Result: Key is valid, but quota/rate limit is exhausted (429).")
            print("Action: wait/reset quota or upgrade quota, then re-run.")
        elif auth_valid:
            print("Result: Key is valid, but pipeline/native generation probe failed.")
            print("Action: verify model name, project permissions, and API availability.")
        elif openai_result.ok:
            print("Result: Key works for OpenAI-compatible endpoint, but NOT for pipeline/native flow.")
            print("Action: Use a valid native Gemini API key for this project flow, or change provider implementation.")
        else:
            print("Result: FAIL for both native and OpenAI-compatible Gemini probes.")
            print("Action: Regenerate key in Google AI Studio and verify API access/project binding.")

    # Exit codes are tuned for CI and quick shell checks.
    # 0: required mode passed
    # 1: required mode failed
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
