from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import RuntimeConfig, load_runtime_config
from src.extractor.vlm_client import VLMClient
from src.extractor.vlm_extractor import ExtractionAttempt, run_stage5_extraction
from src.index.colpali_indexer import ColPaliIndexer
from src.ingest.pdf_page_renderer import render_pdf_page
from src.orchestration.cove_loop import run_cove_loop
from src.retrieval.hybrid_retriever import retrieve_top_pages
from src.synthesis.synthesize import _synthesize_register, _write_audit_trace, _write_driver_c, _write_driver_h
from src.validator.svd_validator import load_svd_registers

DATA_ROOT = ROOT / "data"
DATASHEET_DIR = DATA_ROOT / "datasheets"
SVD_DIR = DATA_ROOT / "svd"
CONFIG_PATH = ROOT / "configs" / "model_config.json"
DEFAULT_UI_OUTDIR = ROOT / "generated" / "ui_runs"


def _is_streamlit_runtime() -> bool:
    """Return True when executed by `streamlit run`, not plain `python`."""
    logger = logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context")
    previous_level = logger.level
    logger.setLevel(logging.ERROR)
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False
    finally:
        logger.setLevel(previous_level)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _list_files(folder: Path, pattern: str) -> list[Path]:
    return sorted([path for path in folder.glob(pattern) if path.is_file()], key=lambda p: p.name.lower())


def _suggest_svd(datasheet: Path, svd_files: list[Path]) -> Path | None:
    stem = datasheet.stem.lower()
    preferred_name = ""

    if "stm32f401" in stem:
        preferred_name = "stm32f401.svd"
    elif "rp2040" in stem:
        preferred_name = "rp2040.svd"

    if preferred_name:
        for svd in svd_files:
            if svd.name.lower() == preferred_name:
                return svd

    for svd in svd_files:
        if svd.stem.lower() in stem:
            return svd

    return svd_files[0] if svd_files else None


def _latest_parsed_attempt(attempts: list[ExtractionAttempt]) -> dict[str, Any] | None:
    for attempt in reversed(attempts):
        if isinstance(attempt.parsed_json, dict) and attempt.parsed_json:
            return attempt.parsed_json
    return None


def _build_page_context(
    datasheet_path: Path,
    top_pages: list[dict[str, Any]],
    render_dir: Path,
) -> list[dict[str, Any]]:
    page_context: list[dict[str, Any]] = []

    for page in top_pages:
        image_path = page.get("image_path")
        if not image_path or not Path(str(image_path)).exists():
            rendered = render_pdf_page(datasheet_path, int(page["page_number"]), render_dir)
            image_path = str(rendered) if rendered is not None else None

        page_context.append(
            {
                "page_id": page["page_id"],
                "source_file": page.get("source_file", datasheet_path.name),
                "page_number": page["page_number"],
                "peripheral": page.get("peripheral", ""),
                "keywords": page.get("keywords", []),
                "page_text": str(page.get("text", ""))[:4000],
                "image_path": str(image_path) if image_path else None,
            }
        )

    return page_context


def _build_attempt_rows(attempts: list[ExtractionAttempt]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for attempt in attempts:
        failed_checks = []
        if attempt.validation_checks:
            failed_checks = [
                name for name, details in attempt.validation_checks.items() if not bool(details.get("ok", True))
            ]

        rows.append(
            {
                "attempt": attempt.attempt,
                "schema_valid": attempt.schema_valid,
                "validation_status": attempt.validation_status or "N/A",
                "failed_checks": ", ".join(failed_checks) if failed_checks else "",
                "schema_error": attempt.schema_errors[0] if attempt.schema_errors else "",
            }
        )

    return rows


def _build_cove_rows(cove_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for attempt in cove_attempts:
        validation = attempt.get("validation", {})
        checks = validation.get("checks", {})
        failed_checks = [name for name, details in checks.items() if not bool(details.get("ok", True))]

        rows.append(
            {
                "attempt": attempt.get("attempt"),
                "status": validation.get("status", "N/A"),
                "failed_checks": ", ".join(failed_checks) if failed_checks else "",
                "message": validation.get("message", ""),
            }
        )

    return rows


def _mcu_family_from_svd(svd_path: Path) -> str:
    stem = svd_path.stem
    if stem.lower() == "stm32f401":
        return "STM32F401"
    if stem.lower() == "rp2040":
        return "RP2040"
    return stem.upper()


def _with_retrieval_override(runtime_cfg: RuntimeConfig, backend: str, top_k: int):
    return runtime_cfg.retrieval.__class__(
        top_k=top_k,
        lexical_weight=runtime_cfg.retrieval.lexical_weight,
        semantic_weight=runtime_cfg.retrieval.semantic_weight,
        hex_token_boost=runtime_cfg.retrieval.hex_token_boost,
        rrf_k=runtime_cfg.retrieval.rrf_k,
        backend=backend,
        colpali_model=runtime_cfg.retrieval.colpali_model,
        colpali_index_path=runtime_cfg.retrieval.colpali_index_path,
    )


def _inject_styles() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --card-bg: rgba(255, 255, 255, 0.85);
  --ink: #0f2a2f;
  --muted: #4a646a;
  --teal: #0d7c86;
  --sand: #ffd89f;
  --mint: #d7f3e3;
  --line: rgba(12, 66, 72, 0.16);
}

.stApp {
  font-family: 'Manrope', sans-serif;
  color: var(--ink);
  background:
    radial-gradient(1200px 450px at 10% -5%, rgba(255, 216, 159, 0.42), transparent 65%),
    radial-gradient(900px 380px at 95% 5%, rgba(13, 124, 134, 0.22), transparent 70%),
    linear-gradient(170deg, #f6fbff 0%, #edf6f3 52%, #fffaf2 100%);
}

.block-container {
  max-width: 1120px;
  padding-top: 1.2rem;
  padding-bottom: 2.2rem;
}

.hero {
  border: 1px solid var(--line);
  background: linear-gradient(120deg, rgba(255, 255, 255, 0.96), rgba(215, 243, 227, 0.7));
  border-radius: 20px;
  padding: 1.2rem 1.3rem;
  margin-bottom: 1.1rem;
  box-shadow: 0 16px 40px rgba(12, 49, 54, 0.09);
}

.hero h1 {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.hero p {
  margin: 0.45rem 0 0;
  color: var(--muted);
  font-size: 0.96rem;
}

[data-testid="stTextArea"],
[data-testid="stSelectbox"],
[data-testid="stTextInput"],
[data-testid="stSlider"] {
  border-radius: 14px;
}

.stCode pre,
code,
[data-testid="stMarkdownContainer"] code {
  font-family: 'JetBrains Mono', monospace;
}

[data-testid="stStatusWidget"] {
  border: 1px solid var(--line);
  border-radius: 16px;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    st.markdown(
        """
<div class="hero">
  <h1>KarcinoJen Pipeline Studio</h1>
  <p>Run a full datasheet-to-driver flow with explicit stage visibility for indexing, extraction, CoVe correction, and generated artifacts.</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_files(files: list[Path]) -> None:
    st.subheader("Output Files")

    for output_file in files:
        with st.expander(output_file.name, expanded=output_file.suffix in {".h", ".c"}):
            content = output_file.read_text(encoding="utf-8")

            if output_file.suffix == ".json":
                try:
                    st.json(json.loads(content))
                except json.JSONDecodeError:
                    st.code(content, language="json")
            elif output_file.suffix in {".h", ".c"}:
                st.code(content, language="c")
            else:
                st.code(content)

            st.download_button(
                label=f"Download {output_file.name}",
                data=content,
                file_name=output_file.name,
                key=f"download_{output_file.name}_{output_file.stat().st_mtime_ns}",
                use_container_width=True,
            )


def main() -> None:
    st.set_page_config(page_title="KarcinoJen UI", page_icon="KB", layout="wide")
    _inject_styles()
    _render_header()

    datasheets = _list_files(DATASHEET_DIR, "*.pdf")
    svd_files = _list_files(SVD_DIR, "*.svd")

    if not datasheets:
        st.error(f"No datasheets found in {DATASHEET_DIR}")
        return
    if not svd_files:
        st.error(f"No SVD files found in {SVD_DIR}")
        return

    config = load_runtime_config(CONFIG_PATH)

    query = st.text_area(
        "Register Query",
        value="Extract GPIOA MODER register bit layout for pins 0 to 3 and include bit widths.",
        height=110,
    )

    left_col, mid_col, right_col = st.columns([1.5, 1, 1])

    selected_datasheet = left_col.selectbox(
        "Datasheet",
        options=datasheets,
        format_func=lambda path: path.name,
    )

    suggested_svd = _suggest_svd(selected_datasheet, svd_files)
    svd_default_index = svd_files.index(suggested_svd) if suggested_svd in svd_files else 0

    selected_svd = mid_col.selectbox(
        "SVD File",
        options=svd_files,
        index=svd_default_index,
        format_func=lambda path: path.name,
    )

    backend_options = ["colpali", "lexical"]
    configured_backend = config.retrieval.backend.lower()
    backend_default_index = backend_options.index(configured_backend) if configured_backend in backend_options else 0

    backend = right_col.selectbox(
        "Retrieval Backend",
        options=backend_options,
        index=backend_default_index,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    top_k = c1.slider("Top-k pages", min_value=1, max_value=10, value=int(config.retrieval.top_k), step=1)
    force_reindex = c2.checkbox("Force re-index", value=False, disabled=(backend != "colpali"))
    output_root = c3.text_input("Output root", value=str(DEFAULT_UI_OUTDIR))

    st.caption(
        f"Active provider from config: {config.selected_provider}/{config.provider.model}"
    )

    run_button = st.button("Run Pipeline", type="primary", use_container_width=True)

    if run_button:
        if not query.strip():
            st.warning("Please enter a query before running the pipeline.")
            return

        retrieval_cfg = _with_retrieval_override(config, backend=backend, top_k=top_k)
        output_dir = Path(output_root) / _utc_stamp()
        output_dir.mkdir(parents=True, exist_ok=True)
        render_cache_dir = output_dir / "_render_cache"
        render_cache_dir.mkdir(parents=True, exist_ok=True)

        stage_data: dict[str, Any] = {}

        try:
            with st.status("1) Indexing", expanded=True) as status:
                if backend == "colpali":
                    index_root = Path(retrieval_cfg.colpali_index_path)
                    if not index_root.is_absolute():
                        index_root = ROOT / index_root

                    indexer = ColPaliIndexer(
                        model_name=retrieval_cfg.colpali_model,
                        index_root=index_root,
                    )
                    manifest_path = index_root / selected_datasheet.stem.lower() / "manifest.json"
                    status.write(f"Index root: {index_root}")

                    if manifest_path.exists() and not force_reindex:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        status.write(
                            f"Reusing index for {selected_datasheet.name} ({manifest.get('total_pages', 0)} pages)."
                        )
                    else:
                        action_text = "Rebuilding" if force_reindex else "Building"
                        status.write(f"{action_text} ColPali index for {selected_datasheet.name}...")
                        manifest = indexer.index_datasheet(selected_datasheet, force=force_reindex)
                        status.write(f"Indexed {manifest.get('total_pages', 0)} pages.")

                    stage_data["index_pages"] = int(manifest.get("total_pages", 0))
                    stage_data["index_stem"] = str(manifest.get("stem", ""))
                    status.update(label="1) Indexing complete", state="complete")
                else:
                    stage_data["index_pages"] = 0
                    stage_data["index_stem"] = "n/a"
                    status.write("Lexical backend selected, so indexing is skipped.")
                    status.update(label="1) Indexing skipped", state="complete")

            with st.status("2) Retrieval", expanded=True) as status:
                top_pages = retrieve_top_pages(
                    query=query,
                    datasheet_path=selected_datasheet,
                    retrieval_cfg=retrieval_cfg,
                )
                if not top_pages:
                    raise RuntimeError("Retrieval returned 0 pages.")

                stage_data["top_pages"] = top_pages
                status.write(f"Retrieved {len(top_pages)} page candidates.")
                for page in top_pages:
                    score_value = page.get("score")
                    score_str = f"score={float(score_value):.3f}" if isinstance(score_value, (int, float)) else ""
                    status.write(f"- page {page['page_number']} ({page['page_id']}) {score_str}")
                status.update(label="2) Retrieval complete", state="complete")

            with st.status("3) Extraction", expanded=True) as status:
                registers = load_svd_registers(str(selected_svd))
                status.write(f"Loaded {len(registers)} registers from {selected_svd.name}.")

                page_context = _build_page_context(selected_datasheet, top_pages, render_cache_dir)

                primary_client = VLMClient(config.provider)

                stage5 = run_stage5_extraction(
                    client=primary_client,
                    fallback_clients=None,
                    extraction_cfg=config.extraction,
                    query=query,
                    page_context=page_context,
                    registers=registers,
                )

                attempt_rows = _build_attempt_rows(stage5.attempts)
                stage_data["extraction_rows"] = attempt_rows
                stage_data["stage5_status"] = stage5.status
                stage_data["registers"] = registers
                stage_data["page_context"] = page_context
                stage_data["primary_client"] = primary_client
                stage_data["stage5"] = stage5

                status.write(
                    f"Extraction status: {stage5.status}. Attempts: {len(stage5.attempts)}."
                )
                status.update(label="3) Extraction complete", state="complete")

            st.subheader("Extraction Attempts")
            st.dataframe(stage_data["extraction_rows"], use_container_width=True)

            with st.status("4) CoVe Correction", expanded=True) as status:
                stage5 = stage_data["stage5"]
                seed_extraction = stage5.extraction or _latest_parsed_attempt(stage5.attempts)
                if seed_extraction is None:
                    raise RuntimeError("CoVe skipped because no schema-valid extraction was produced.")

                cove = run_cove_loop(
                    initial_extraction=seed_extraction,
                    registers=stage_data["registers"],
                    max_attempts=3,
                    vlm_client=stage_data["primary_client"],
                    fallback_clients=None,
                    query=query,
                    page_context=stage_data["page_context"],
                )
                cove_rows = _build_cove_rows(cove.attempts)

                stage_data["cove"] = cove
                stage_data["cove_rows"] = cove_rows

                status.write(f"CoVe status: {cove.status}. Attempts: {len(cove.attempts)}.")
                status.update(label="4) CoVe complete", state="complete")

            st.subheader("CoVe Attempts")
            st.dataframe(stage_data["cove_rows"], use_container_width=True)

            cove = stage_data["cove"]
            if cove.status != "PASS":
                raise RuntimeError(
                    f"CoVe ended with {cove.status}. Review the CoVe attempt table above."
                )

            with st.status("5) Synthesis", expanded=True) as status:
                extra_iterations = max(0, len(cove.attempts) - 1)
                validation_attempts = len(stage_data["stage5"].attempts) + extra_iterations

                validated_payload = {
                    **cove.final_extraction,
                    "validation_status": "PASS",
                    "validation_attempts": validation_attempts,
                    "source_page_id": top_pages[0]["page_id"],
                    "source_file": selected_datasheet.name,
                    "mcu_family": _mcu_family_from_svd(selected_svd),
                }

                synth = _synthesize_register(validated_payload)
                if synth is None:
                    raise RuntimeError("Synthesis failed because extraction is not validation-ready.")

                driver_h = output_dir / "driver.h"
                driver_c = output_dir / "driver.c"
                audit_trace = output_dir / "audit_trace.json"

                _write_driver_h([synth], str(driver_h))
                _write_driver_c([synth], "driver.h", str(driver_c))
                _write_audit_trace(
                    [synth],
                    [f"UI run: {selected_datasheet.name} + {selected_svd.name}"],
                    str(audit_trace),
                )

                stage_data["output_files"] = [driver_h, driver_c, audit_trace]
                stage_data["validated_payload"] = validated_payload

                status.write(f"Artifacts written under: {output_dir}")
                status.update(label="5) Synthesis complete", state="complete")

            metric_a, metric_b, metric_c, metric_d = st.columns(4)
            metric_a.metric("Retrieved pages", value=len(stage_data["top_pages"]))
            metric_b.metric("Extraction attempts", value=len(stage_data["extraction_rows"]))
            metric_c.metric("CoVe attempts", value=len(stage_data["cove_rows"]))
            metric_d.metric("Output files", value=len(stage_data["output_files"]))

            st.success(f"Pipeline completed successfully. Output folder: {output_dir}")

            st.subheader("Final Validated Extraction")
            st.json(stage_data["validated_payload"])

            st.subheader("Retrieved Pages")
            retrieval_table = [
                {
                    "page_id": page.get("page_id"),
                    "page_number": page.get("page_number"),
                    "source_file": page.get("source_file"),
                    "score": page.get("score", ""),
                    "method": page.get("retrieval_method", ""),
                }
                for page in stage_data["top_pages"]
            ]
            st.dataframe(retrieval_table, use_container_width=True)

            _render_files(stage_data["output_files"])

        except Exception as exc:
            st.error(f"Pipeline failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    if not _is_streamlit_runtime():
        script_path = Path(__file__).resolve()
        print("This UI must be launched with Streamlit.")
        print("Run:")
        print(f"  streamlit run {script_path}")
        sys.exit(0)
    main()
