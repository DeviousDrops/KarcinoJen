"""
KarcinoJen end-to-end test harness.
Runs multiple queries against multiple datasheets and reports
retrieval quality, extraction pass/fail, and synthesis output.
"""
import argparse
import logging
import os
import sys
import time
import tempfile
import traceback
from urllib import error, request
from urllib.parse import urlparse
from pathlib import Path
from dataclasses import dataclass, field, replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extractor.model_config import load_runtime_config
from src.extractor.vlm_client import VLMClient
from src.extractor.vlm_extractor import run_stage5_extraction
from src.extractor.schema_harness import validate_register_extraction
from src.ingest.pdf_page_renderer import render_pdf_page
from src.orchestration.cove_loop import run_cove_loop
from src.retrieval.hybrid_retriever import retrieve_top_pages
from src.validator.svd_validator import load_svd_registers, validate_extraction
from src.validator.error_taxonomy import classify_failure
from src.evaluation.pass_at_k import compute_pass_at_k
from src.synthesis.llm_enrichment import enrich_driver_with_fallback
from src.synthesis.synthesize import _synthesize_register, _write_driver_h, _write_driver_c

def green(s):  return s
def red(s):    return s
def yellow(s): return s
def cyan(s):   return s
def bold(s):   return s

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
PARTIAL = "PARTIAL"

LOGGER = logging.getLogger(__name__)


def _latest_parsed_attempt(attempts):
    for attempt in reversed(attempts):
        if isinstance(attempt.parsed_json, dict) and attempt.parsed_json:
            return attempt.parsed_json
    return None


def _build_extraction_fallback_clients(cfg) -> list[VLMClient]:
    clients: list[VLMClient] = []
    seen: set[str] = set()

    def _is_endpoint_reachable(endpoint_url: str) -> bool:
        raw = endpoint_url.strip()
        if not raw:
            return False
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return False
        probe_url = f"{parsed.scheme}://{parsed.netloc}"
        req = request.Request(probe_url, method="GET")
        try:
            request.urlopen(req, timeout=1.5)
            return True
        except error.HTTPError:
            # HTTP response means service is reachable.
            return True
        except Exception:
            return False

    def _add(provider_name: str) -> None:
        if provider_name in seen:
            return
        provider_cfg = cfg.providers.get(provider_name)
        if provider_cfg is None:
            return

        if provider_name in ("llava", "qwen2_5_vl") and provider_cfg.endpoint_env:
            endpoint = os.getenv(provider_cfg.endpoint_env, "").strip()
            if not endpoint:
                endpoint = "http://localhost:11434/api/generate"
            if not _is_endpoint_reachable(endpoint):
                LOGGER.warning(
                    "Skipping %s fallback: endpoint not reachable at %s",
                    provider_name,
                    endpoint,
                )
                return

        clients.append(VLMClient(provider_cfg))
        seen.add(provider_name)

    if cfg.selected_provider == "gemini":
        # Gemini-only test mode: do not add local VLM fallbacks.
        return clients
    elif cfg.selected_provider in ("llava", "qwen2_5_vl"):
        _add("qwen2_5_vl" if cfg.selected_provider == "llava" else "llava")
        _add("gemini")
    elif cfg.selected_provider == "openai":
        _add("gemini")
        _add("qwen2_5_vl")
        _add("llava")
    elif cfg.selected_provider == "groq":
        _add("gemini")
        _add("qwen2_5_vl")
        _add("llava")

    return clients


def _build_llm_enrichment_clients(cfg) -> list[VLMClient]:
    clients: list[VLMClient] = []

    def _is_endpoint_reachable(endpoint_url: str) -> bool:
        raw = endpoint_url.strip()
        if not raw:
            return False
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return False
        probe_url = f"{parsed.scheme}://{parsed.netloc}"
        req = request.Request(probe_url, method="GET")
        try:
            request.urlopen(req, timeout=1.5)
            return True
        except error.HTTPError:
            return True
        except Exception:
            return False

    for provider_name in ("groq", "ollama", "qwen2_5_vl", "llava"):
        provider_cfg = cfg.providers.get(provider_name)
        if provider_cfg is not None:
            if provider_name in ("ollama", "llava", "qwen2_5_vl") and provider_cfg.endpoint_env:
                endpoint = os.getenv(provider_cfg.endpoint_env, "").strip()
                if not endpoint:
                    endpoint = (
                        "http://localhost:11434/api/chat"
                        if provider_name == "ollama"
                        else "http://localhost:11434/api/generate"
                    )
                if not _is_endpoint_reachable(endpoint):
                    LOGGER.warning(
                        "Skipping %s enrichment client: endpoint not reachable at %s",
                        provider_name,
                        endpoint,
                    )
                    continue
            clients.append(VLMClient(provider_cfg))
    return clients

# ── test cases ────────────────────────────────────────────────────────────────
TEST_CASES = [
    # (label, datasheet_stem, svd_stem, query, expected_peripheral, expected_register)
    (
        "STM32 · GPIOA MODER",
        "stm32f401-rm",
        "stm32f401",
        "Extract GPIOA MODER register bit layout for pins 0 to 3 with mode encoding width per pin.",
        "GPIOA", "MODER",
    ),
    (
        "STM32 · USART2 CR1",
        "stm32f401-rm",
        "stm32f401",
        "Extract USART2 CR1 control bits including UE, M, PCE, TE, and RE with bit positions.",
        "USART2", "CR1",
    ),
    (
        "STM32 · RCC AHB1ENR",
        "stm32f401-rm",
        "stm32f401",
        "Extract RCC AHB1ENR register GPIOAEN bit and GPIOBEN bit positions.",
        "RCC", "AHB1ENR",
    ),
    (
        "STM32 · TIM2 CR1",
        "stm32f401-rm",
        "stm32f401",
        "Extract TIM2 CR1 register bits: CEN, UDIS, URS, OPM, DIR with positions and widths.",
        "TIM2", "CR1",
    ),
    (
        "RP2040 · SIO GPIO_OUT",
        "RP2040-datasheet",
        "RP2040",
        "Extract SIO GPIO_OUT register base address, offset, and bit layout for GPIO output control.",
        "SIO", "GPIO_OUT",
    ),
]

@dataclass
class TestResult:
    label: str
    retrieval_ok: bool = False
    retrieval_pages: list[str] = field(default_factory=list)
    extraction_status: str = "NOT_RUN"
    extraction_attempts: int = 0
    schema_valid: bool = False
    svd_status: str = "N/A"
    synthesis_ok: bool = False
    driver_h_lines: int = 0
    driver_c_lines: int = 0
    llm_enriched: bool = False
    llm_provider: str = "N/A"
    pass_k_accuracy: float | None = None
    pass_k_matched: int = 0
    pass_k_total: int = 0
    error_category: str | None = None
    error: str = ""
    elapsed_s: float = 0.0

    def overall(self):
        if self.error:
            return FAIL
        if self.extraction_status == "PASS" and self.synthesis_ok:
            return PASS
        if self.extraction_status == "PASS":
            return PARTIAL
        return FAIL


def run_one(
    label,
    datasheet_stem,
    svd_stem,
    query,
    expected_peripheral,
    expected_register,
    cfg,
) -> TestResult:
    result = TestResult(label=label)
    t0 = time.perf_counter()

    try:
        ds_path = ROOT / "data" / "datasheets" / f"{datasheet_stem}.pdf"
        svd_path = ROOT / "data" / "svd" / f"{svd_stem}.svd"

        if not ds_path.exists():
            result.error = f"Datasheet not found: {ds_path.name}"
            return result
        if not svd_path.exists():
            result.error = f"SVD not found: {svd_path.name}"
            return result

        # ── Stage 1: Retrieval ───────────────────────────────────────────────
        retrieval_t0 = time.perf_counter()
        print("  [stage] retrieval started...", flush=True)
        top_pages = retrieve_top_pages(
            query=query, datasheet_path=ds_path, retrieval_cfg=cfg.retrieval
        )
        retrieval_elapsed = time.perf_counter() - retrieval_t0
        print(f"  [stage] retrieval done in {retrieval_elapsed:.1f}s", flush=True)
        result.retrieval_ok = len(top_pages) > 0
        result.retrieval_pages = [p["page_id"] for p in top_pages]

        if not top_pages:
            result.error = "Retrieval returned 0 pages"
            return result

        # ── Stage 2: Render + build page context ─────────────────────────────
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            page_context = []
            for p in top_pages:
                img = render_pdf_page(ds_path, int(p["page_number"]), td_path / "imgs")
                page_context.append({
                    "page_id":     p["page_id"],
                    "source_file": p["source_file"],
                    "page_number": p["page_number"],
                    "peripheral":  p["peripheral"],
                    "keywords":    p.get("keywords", []),
                    "page_text":   str(p.get("text", ""))[:3000],
                    "image_path":  str(img) if img else None,
                })

            # ── Stage 3: VLM extraction with validation ─────────────────────
            registers = load_svd_registers(str(svd_path))
            primary_client = VLMClient(cfg.provider)
            fallback_clients = _build_extraction_fallback_clients(cfg)

            stage5 = run_stage5_extraction(
                client=primary_client,
                fallback_clients=fallback_clients or None,
                extraction_cfg=cfg.extraction,
                query=query,
                page_context=page_context,
                registers=registers,
            )
            print(
                f"  [stage] extraction done: status={stage5.status} attempts={len(stage5.attempts)}",
                flush=True,
            )

            result.extraction_status = stage5.status
            result.extraction_attempts = len(stage5.attempts)

            extraction_payload = stage5.extraction
            cove_outcome = None
            seed_extraction = extraction_payload or _latest_parsed_attempt(stage5.attempts)
            if seed_extraction is not None:
                print("  [stage] cove started...", flush=True)
                cove_outcome = run_cove_loop(
                    initial_extraction=seed_extraction,
                    registers=registers,
                    max_attempts=3,
                    vlm_client=primary_client,
                    fallback_clients=fallback_clients or None,
                    query=query,
                    page_context=page_context,
                )
                print(
                    f"  [stage] cove done: status={cove_outcome.status} attempts={len(cove_outcome.attempts)}",
                    flush=True,
                )
                # The first CoVe attempt validates the seed extraction; count only extra retries.
                extra_iterations = max(0, len(cove_outcome.attempts) - 1)
                result.extraction_attempts += extra_iterations
                result.extraction_status = cove_outcome.status
                if cove_outcome.status == "PASS":
                    extraction_payload = cove_outcome.final_extraction
                else:
                    extraction_payload = None
            else:
                print("  [stage] cove skipped: no seed extraction available", flush=True)

            if result.extraction_status != "PASS" or extraction_payload is None:
                # Collect failure details for diagnosis
                fail_reasons = []
                for att in stage5.attempts:
                    if not att.raw_text:
                        # schema_errors[0] holds the exception str when the client threw
                        exc_msg = att.schema_errors[0] if att.schema_errors else "empty response"
                        fail_reasons.append(f"attempt {att.attempt}: {exc_msg[:120]}")
                    elif att.schema_errors:
                        fail_reasons.append(f"attempt {att.attempt}: schema {att.schema_errors[0]}")
                    elif att.validation_status and att.validation_status != "PASS":
                        checks = att.validation_checks or {}
                        bad = [k for k, v in checks.items() if not v.get("ok", True)]
                        fail_reasons.append(f"attempt {att.attempt}: SVD FAIL checks={bad}")

                if cove_outcome is None:
                    fail_reasons.append("cove_loop: no schema-valid extraction to seed retries")
                elif cove_outcome.status != "PASS":
                    fail_reasons.append(
                        f"cove_loop: {cove_outcome.status} after {len(cove_outcome.attempts)} attempts"
                    )

                result.error = "Extraction FAIL. " + " | ".join(fail_reasons) if fail_reasons else "Extraction FAIL."
                return result

            ext = extraction_payload
            schema_result = validate_register_extraction(ext)
            result.schema_valid = schema_result.is_valid

            svd_result = validate_extraction(ext, registers)
            result.svd_status = svd_result.status
            if svd_result.status != "PASS":
                result.error_category = classify_failure(svd_result.checks)

            # Quick check: peripheral/register close to expected
            got_p = str(ext.get("peripheral", "")).upper()
            got_r = str(ext.get("register_name", "")).upper()
            if expected_peripheral.upper() not in got_p and got_p not in expected_peripheral.upper():
                result.error = f"Wrong peripheral extracted: got '{got_p}', expected '{expected_peripheral}'"
                # don't return — still synthesize so we can see output
            if expected_register.upper() not in got_r and got_r not in expected_register.upper():
                if result.error:
                    result.error += f" | Wrong register extracted: got '{got_r}', expected '{expected_register}'"
                else:
                    result.error = f"Wrong register extracted: got '{got_r}', expected '{expected_register}'"

            # ── Stage 4: Synthesis ───────────────────────────────────────────
            validated_payload = {
                **ext,
                "validation_status":   "PASS",
                "validation_attempts": result.extraction_attempts,
                "source_page_id":      top_pages[0]["page_id"],
                "source_file":         ds_path.name,
                "mcu_family":          svd_stem.upper(),
            }

            synth = _synthesize_register(validated_payload)
            if synth is not None:
                out_dir = td_path / "out"
                out_dir.mkdir()
                h_file = out_dir / "driver.h"
                c_file = out_dir / "driver.c"
                h_path = str(h_file)
                c_path = str(c_file)
                _write_driver_h([synth], h_path)
                _write_driver_c([synth], "driver.h", c_path)
                result.driver_h_lines = len(Path(h_path).read_text().splitlines())
                result.driver_c_lines = len(Path(c_path).read_text().splitlines())
                result.synthesis_ok = True

                llm_ok, llm_provider_or_reason = enrich_driver_with_fallback(
                    validated_payload=validated_payload,
                    driver_h_path=h_file,
                    driver_c_path=c_file,
                    clients=_build_llm_enrichment_clients(cfg),
                )
                result.llm_enriched = llm_ok
                result.llm_provider = llm_provider_or_reason
                if not llm_ok:
                    result.error = (
                        f"LLM enrichment failed: {llm_provider_or_reason}"
                        if not result.error
                        else result.error + f" | LLM enrichment failed: {llm_provider_or_reason}"
                    )

                pass_report = compute_pass_at_k(
                    h_path,
                    svd_path,
                    peripheral_filter=expected_peripheral,
                )
                result.pass_k_accuracy = float(pass_report.get("accuracy", 0.0))
                result.pass_k_matched = int(pass_report.get("matched", 0))
                result.pass_k_total = int(pass_report.get("total_defines", 0))

    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        if "--verbose" in sys.argv:
            traceback.print_exc()
    finally:
        result.elapsed_s = round(time.perf_counter() - t0, 1)

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KarcinoJen VLM+CoVe+LLM pipeline test harness")
    parser.add_argument(
        "--backend",
        choices=["colpali", "lexical"],
        default=None,
        help="Override retrieval backend for this test run",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override retrieval top-k",
    )
    parser.add_argument(
        "--case",
        type=int,
        default=None,
        help="Run only one 1-based test case index",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Keep third-party noise manageable while preserving our Stage logs.
    for noisy in [
        "urllib3",
        "httpx",
        "huggingface_hub",
        "transformers",
        "torch",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main():
    args = build_parser().parse_args()
    _configure_logging(args.verbose)

    cfg = load_runtime_config(ROOT / "configs" / "model_config.json")
    retrieval_cfg = cfg.retrieval
    if args.backend is not None:
        retrieval_cfg = replace(retrieval_cfg, backend=args.backend)
    if args.top_k is not None:
        retrieval_cfg = replace(retrieval_cfg, top_k=max(1, args.top_k))
    if retrieval_cfg is not cfg.retrieval:
        cfg = replace(cfg, retrieval=retrieval_cfg)

    selected_cases = TEST_CASES
    if args.case is not None:
        if args.case < 1 or args.case > len(TEST_CASES):
            raise SystemExit(f"--case must be in range 1..{len(TEST_CASES)}")
        selected_cases = [TEST_CASES[args.case - 1]]

    print()
    print(bold("=" * 72))
    print(bold(f"  KarcinoJen VLM + CoVe + LLM Test Suite"))
    print(bold(f"  Provider: {cfg.selected_provider} / {cfg.provider.model}"))
    print(bold(f"  Retrieval backend: {cfg.retrieval.backend}  top_k={cfg.retrieval.top_k}"))
    print(bold("  CoVe loop: enabled"))
    print(bold("  LLM enrichment: required"))
    print(bold("=" * 72))

    results: list[TestResult] = []
    for i, tc in enumerate(selected_cases, 1):
        label, ds, svd, query, exp_p, exp_r = tc
        print(f"\n[{i}/{len(selected_cases)}] {label}")
        print(f"  Query: {query[:80]}...")
        r = run_one(label, ds, svd, query, exp_p, exp_r, cfg)
        results.append(r)

        print(f"  Retrieval : {'OK' if r.retrieval_ok else 'FAIL'} | pages: {r.retrieval_pages[:3]}")
        print(f"  Extraction: {r.extraction_status} (attempts={r.extraction_attempts})")
        print(f"  SVD       : {r.svd_status}")
        print(f"  Synthesis : {'OK' if r.synthesis_ok else ('SKIP' if r.extraction_status != 'PASS' else 'FAIL')}"
              f"  | driver.h={r.driver_h_lines}L  driver.c={r.driver_c_lines}L")
        print(f"  LLM       : {'OK' if r.llm_enriched else 'FAIL'}"
              f"  | provider={r.llm_provider}")
        if r.pass_k_accuracy is None:
            print("  PASS@K    : N/A")
        else:
            print(
                f"  PASS@K    : {r.pass_k_accuracy*100:.1f}% "
                f"({r.pass_k_matched}/{r.pass_k_total})"
            )
        if r.error_category:
            print(f"  Taxonomy  : {r.error_category}")
        if r.error:
            print(f"  Error: {r.error}")
        print(f"  Overall   : {r.overall()}  [{r.elapsed_s}s]")

        # Brief pause between tests to avoid hitting Groq TPM rate limits
        if i < len(selected_cases):
            time.sleep(3)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed  = sum(1 for r in results if r.overall() == PASS)
    partial = sum(1 for r in results if r.overall() == PARTIAL)
    failed  = len(results) - passed - partial

    print()
    print("=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    for r in results:
        status_char = "OK" if r.overall() == PASS else ("~~" if r.overall() == PARTIAL else "XX")
        print(f"  [{status_char}]  {r.label:<35s}  {r.elapsed_s:>5.1f}s  {r.overall()}")

    print()
    print(f"  Passed: {green(str(passed))}  Partial: {yellow(str(partial))}  Failed: {red(str(failed))}")
    total = len(results)
    print(f"  Score : {passed}/{total}  ({100*passed//total}%)")

    passk_values = [r.pass_k_accuracy for r in results if r.pass_k_accuracy is not None]
    if passk_values:
        mean_passk = sum(passk_values) / len(passk_values)
        print(f"  Mean PASS@K: {mean_passk*100:.1f}%")

    taxonomy_counts: dict[str, int] = {
        "Address Drift": 0,
        "Layout Confusion": 0,
        "Context Bleed": 0,
        "Uncategorized": 0,
    }
    for r in results:
        if r.error_category and r.error_category in taxonomy_counts:
            taxonomy_counts[r.error_category] += 1

    print(
        "  Error taxonomy: "
        f"Address Drift={taxonomy_counts['Address Drift']}, "
        f"Layout Confusion={taxonomy_counts['Layout Confusion']}, "
        f"Context Bleed={taxonomy_counts['Context Bleed']}, "
        f"Uncategorized={taxonomy_counts['Uncategorized']}"
    )
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
