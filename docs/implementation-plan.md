# KarcinoJen

## Implementation Plan

KarcinoJen is a paper-first research prototype that generates verifiable C driver snippets from vendor MCU datasheet PDFs using a visual-first RAG pipeline, prompt engineering, and deterministic CMSIS-SVD checks.

For the IEEE draft, the canonical claim is multimodal-first retrieval (ColPali) feeding a VLM extractor, followed by deterministic CoVe validation and text-LLM synthesis.

## Project Goal

Create an end-to-end system that:
- Ingests raw datasheet PDFs without OCR.
- Retrieves relevant register pages using visual and lexical hybrid retrieval.
- Extracts register definitions (and optional timing constraints) with a VLM into strict JSON.
- Validates core register facts against CMSIS-SVD with deterministic checks.
- Synthesizes traceable C driver artifacts for a limited demo query set.
- Produces paper-ready evidence (tables, ablations, error analysis) within a 2-day sprint.

## Scope

In scope:
- Stage 1 to Stage 9 minimal pipeline implementation for demo.
- Offline indexing and online query/extraction for one MCU family.
- Deterministic validator and bounded correction loop.
- Register-focused C code generation with provenance trace.

Out of scope (initial version):
- Full HAL abstraction layers.
- Full production hardening and deployment SLOs.
- Broad MCU coverage beyond selected demo targets.
- Runtime flashing/integration on target hardware.

## Research Constraints for Publishability

- No model fine-tuning in this project timeline.
- Methodology is zero-shot extraction with deterministic grounding.
- Novelty claim is architectural and procedural: hybrid retrieval plus SVD validation plus CoVe loop, enabled by disciplined prompt engineering.
- Model weights are treated as fixed black-box APIs.

Rationale:
- Two-day scope cannot support reliable multimodal fine-tuning data collection and training.
- Controlled prompting plus deterministic validation is the core scientific hypothesis.

## Architecture Summary

| Stage | Mode | Component | Key Output |
|---|---|---|---|
| 1 | Offline | PDF page renderer (300 dpi) | Page images |
| 2 | Offline | ColPali visual encoder | Patch embeddings (multi-vector) |
| 3 | Offline | ColPali local index store | Stored page vectors + image + metadata |
| 4 | Online | Hybrid retrieval (MaxSim + BM25 hex boost + RRF) | Top-k relevant page images |
| 5 | Online | VLM register and timing extractor (Gemini primary; LLaVA/Qwen2.5-VL fallback) | Structured register+timing JSON |
| 6 | Online | SVD + timing symbolic validator | Pass/fail + mismatch report |
| 7 | Online (fail path) | CoVe correction loop (max 3) | Corrected JSON or UNCERTAIN |
| 8 | Online | Text-LLM synthesis and enrichment (Groq primary, local fallback) | driver.h + driver.c + audit_trace.json |
| 9 | Output | Verification and scoring | PASS@K and final deliverables |

## IEEE Draft Update: Modality And Runtime Profiles

Canonical profile (paper claim):
- Retrieval: ColPali MaxSim fused with lexical evidence.
- Extraction: VLM consumes retrieved page images.
- Guardrails: deterministic SVD checks and CoVe retries.
- Generation: text LLM synthesizes and enriches C code from validated JSON.

Why the VLM is still essential:
- Datasheet truth is often encoded in tables and layout, not plain text spans.
- Multimodal retrieval selects visually relevant pages before extraction.
- The VLM reads the page image structure directly; text snippets are auxiliary hints.

Resource-constrained profile (ablation/fallback only):
- Retrieval runs in lexical mode when ColPali is unavailable.
- Retrieved pages are still rendered and sent as images to the VLM.
- This mode is valid for robustness experiments but not the primary architecture claim.

Recommended reproducible runtime:
- Use a Google Colab GPU runtime for canonical ColPali experiments.
- Keep local CPU/low-VRAM runs for fallback baselines and quick iteration.

## Two-Day Prompt-Engineering Sprint

### Day 1: Reliability Core (Prompt + Validation)
Tasks:
- Select one MCU family and 1 to 2 datasheets.
- Add matching CMSIS-SVD files and freeze a compact `MCU-Bench` subset.
- Engineer strict extraction prompts and validate JSON conformance.
- Implement deterministic validator checks and mismatch reports.
- Add CoVe retry loop (max 3) driven by validator feedback.

Exit criteria:
- A small benchmark subset consistently reaches schema-valid, validator-passing JSON.
- Failure examples are captured with taxonomy labels and correction outcomes.

### Day 2: Paper Assets + Minimal Demo
Tasks:
- Generate `driver.h`, `driver.c`, and `audit_trace.json` from validated JSON.
- Run three configurations (Vanilla, no-CoVe, Full) on the same query list.
- Build PASS@K summary, ablation deltas, and qualitative error table.
- Package a one-command demo script; if live E2E is unstable, package deterministic replay artifacts.

Exit criteria:
- Paper-ready methodology and results tables are complete.
- Demo can be shown live or replayed from saved artifacts with clear provenance.

## MCU-Bench: Benchmark Dataset Definition

Name:
- MCU-Bench: A Multimodal Benchmark for Hardware Interface Synthesis.

Target size (demo release):
- 15 to 20 benchmark items.

Each benchmark item contains:
- One rendered datasheet page image.
- One natural language hardware query.
- One hand-verified ground-truth JSON.
- Metadata: MCU family, peripheral, register name, source page id.

Dataset release package:
- `data/mcu-bench/queries.jsonl`
- `data/mcu-bench/ground_truth.jsonl`
- `data/mcu-bench/pages/` (or a reconstruction script if redistribution is restricted)
- `data/mcu-bench/README.md` with annotation protocol.

Licensing note:
- If vendor terms do not allow page-image redistribution, release file/page references and scripts to reconstruct benchmark images from publicly available PDFs.

## Evaluation Protocol and Baselines

All methods run on the same MCU-Bench split and same query list.

Baseline 1: Vanilla VLM
- Input: page image + query + basic extraction prompt.
- No deterministic validator in control path.
- No CoVe correction loop.

Baseline 2: KarcinoJen without CoVe
- Full retrieval and SVD validation enabled.
- Stage 7 disabled. Validation failure remains failure.

Baseline 3: Resource-constrained retrieval ablation
- Retrieval backend forced to lexical with all later stages unchanged.
- Measures how much multimodal retrieval contributes versus fallback retrieval.

Proposed method: Full KarcinoJen
- Full pipeline with SVD validation and CoVe retries (max 3).

Primary table in paper:
- PASS@K for Baseline 1, Baseline 2, Baseline 3, and Full system.
- Absolute and relative gain from fallback retrieval to multimodal retrieval.
- CoVe recovery delta with and without multimodal retrieval.

## Proposed Repository Layout

```text
KarcinoJen/
  README.md
  docs/
    README.md
    architecture.md
    implementation-plan.md
    problem-statement.md
    work-split.md
  data/
    datasheets/
    svd/
  schemas/
    register_extraction.schema.json
    timing_constraints.schema.json
    validator_report.schema.json
  src/
    ingest/
    index/
    retrieval/
    extractor/
    validator/
    synthesis/
    orchestration/
  tests/
    unit/
    integration/
    regression/
  scripts/
  .github/
    workflows/
```

## Metrics and Quality Gates

Primary metric:
- PASS@K: address-level correctness in `driver.h` against SVD ground truth.
- Delta PASS@K versus both baselines.

Supporting metrics:
- Retrieval Recall@K on labeled query-page pairs.
- JSON validity rate from extractor.
- Validator catch rate on curated fail cases.
- CoVe recovery rate after first fail.
- Demo completion rate over target query set.
- Invalid-hex error rate before and after validation.

Quality gates:
- No code synthesis from unvalidated JSON.
- Retry loop hard limit of 3.
- Full provenance required for every emitted define.
- End-to-end demo must run reproducibly on one machine.
- Baseline and ablation outputs must be reproducible from saved run configs.

## Qualitative Error Taxonomy (Paper Section)

Required categories:
- Address Drift: near-miss hexadecimal values (example: `0x40004404` vs `0x40004400`).
- Layout Confusion: merged-cell or row/column boundary mistakes in bit-field tables.
- Context Bleed: extraction from adjacent peripherals on same page.

For each category report:
- One failure example from Baseline 1.
- Whether Stage 6 validator catches it.
- Whether Stage 7 CoVe loop corrects it.

## Risks and Mitigations

- Risk: visually similar but wrong register pages retrieved.
  Mitigation: hybrid retrieval + RRF + hex-token boosting.

- Risk: local GPU memory exhaustion during ColPali indexing/retrieval.
  Mitigation: default canonical experiments to Google Colab GPU runtime; keep lexical fallback profile for local runs.

- Risk: VLM hallucinated addresses or bit fields.
  Mitigation: strict schema validation + SVD deterministic checks.

- Risk: timing table values extracted with wrong units or ambiguous conditions.
  Mitigation: unit normalization, monotonicity checks, and conflict detection before synthesis.

- Risk: two-day schedule cannot support full production hardening.
  Mitigation: prioritize a narrow demo query set and document known limitations.

- Risk: silent propagation of wrong outputs.
  Mitigation: fail-closed behavior and UNCERTAIN routing.

## Immediate Next Steps

1. Freeze a narrow benchmark set (10 to 20 queries) for one MCU family.
2. Finalize prompt templates for extraction, correction, and synthesis with versioned run notes.
3. Prioritize validator and CoVe reliability before expanding benchmark coverage.
4. Keep synthesis deterministic and traceable for paper evidence.
5. Use the Colab notebook path for canonical multimodal runs and local fallback runs for ablations.
