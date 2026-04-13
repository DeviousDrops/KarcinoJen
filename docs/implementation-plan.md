# KarcinoJen

## Implementation Plan

KarcinoJen builds verifiable C drivers from vendor MCU datasheet PDFs using a visual-first RAG pipeline plus deterministic CMSIS-SVD validation.

## Project Goal

Create an end-to-end system that:
- Ingests raw datasheet PDFs without OCR.
- Retrieves relevant register pages using visual and lexical hybrid retrieval.
- Extracts register definitions and timing constraints with a VLM into strict JSON.
- Validates register facts against CMSIS-SVD and timing facts with deterministic symbolic checks.
- Synthesizes traceable C driver artifacts only from validated data.

## Scope

In scope:
- Stage 1 to Stage 9 pipeline implementation.
- Offline indexing and online query/extraction.
- Deterministic validator and bounded correction loop.
- Timing constraint extraction and normalization for supported peripherals.
- C code generation with provenance trace.

Out of scope (initial version):
- Full HAL abstraction layers.
- Auto-generated unit test frameworks for all MCUs.
- Runtime flashing/integration on target hardware.

## Architecture Summary

| Stage | Mode | Component | Key Output |
|---|---|---|---|
| 1 | Offline | PDF page renderer (300 dpi) | Page images |
| 2 | Offline | ColPali visual encoder | Patch embeddings (multi-vector) |
| 3 | Offline | ChromaDB visual index | Stored page vectors + image + metadata |
| 4 | Online | Hybrid retrieval (MaxSim + BM25 hex boost + RRF) | Top-k relevant page images |
| 5 | Online | VLM register and timing extractor (LLaVA/GPT-4V) | Structured register+timing JSON |
| 6 | Online | SVD + timing symbolic validator | Pass/fail + mismatch report |
| 7 | Online (fail path) | CoVe correction loop (max 3) | Corrected JSON or UNCERTAIN |
| 8 | Online | Code synthesis agent | driver.h + driver.c + audit_trace.json |
| 9 | Output | Verification and scoring | PASS@K and final deliverables |

## Implementation Milestones

### Milestone 0: Repo and Data Setup (Week 1)
Tasks:
- Define repository layout and config conventions.
- Add sample datasheets and CMSIS-SVD files for baseline MCUs.
- Add JSON schemas for extractor and validator I/O.

Exit criteria:
- `data/` and `schemas/` are versioned.
- One dry-run sample pipeline config exists.

### Milestone 1: Offline Visual Index Pipeline (Week 2)
Tasks:
- Implement PDF to page-image renderer at 300 dpi.
- Integrate ColPali embedding job for page patch vectors.
- Persist page entries in ChromaDB with metadata and image blob.

Exit criteria:
- A datasheet can be indexed end-to-end.
- Re-indexing avoids duplicate page entries.

### Milestone 2: Hybrid Retrieval Service (Week 3)
Tasks:
- Implement late-interaction retrieval using query-to-patch MaxSim.
- Implement BM25 keyword retrieval with `0x[0-9A-Fa-f]+` boost.
- Fuse ranked lists with Reciprocal Rank Fusion.

Exit criteria:
- Retrieval endpoint returns top-k pages and score traces.
- Known register queries return expected pages in top 5.

### Milestone 3: VLM Extraction Service (Week 4)
Tasks:
- Build extraction prompt template with strict JSON-only output for registers and timing tables.
- Add parser and schema validation for VLM responses.
- Add `timing_constraints` schema tuple (`name`, `min`, `typ`, `max`, `unit`, `condition`).
- Support LLaVA and GPT-4V provider adapters.

Exit criteria:
- Extractor produces schema-valid register and timing JSON for baseline pages.
- Non-JSON VLM outputs are safely rejected and logged.

### Milestone 4: SVD Validator + CoVe Loop (Week 5)
Tasks:
- Implement checks: address range, bit arithmetic/overlap, name fuzzy-match.
- Implement timing checks: unit normalization, min/typ/max monotonicity, duplicate/conflict detection.
- Emit structured mismatch reports with machine-readable reasons.
- Implement bounded retry loop (max 3), then UNCERTAIN escalation.

Exit criteria:
- Validator catches injected errors reliably.
- Timing mismatches are detected and reported with deterministic reasons.
- CoVe loop improves correction success rate on baseline set.

### Milestone 5: Code Synthesis + Traceability (Week 6)
Tasks:
- Generate `driver.h` and `driver.c` from validated JSON.
- Emit `audit_trace.json` mapping each define to SVD entry and page source.
- Add deterministic formatting and stable symbol naming.

Exit criteria:
- Generated code compiles for baseline examples.
- Every generated register symbol has provenance in audit trace.

### Milestone 6: Evaluation and Hardening (Week 7)
Tasks:
- Compute PASS@K by diffing generated addresses vs SVD truth.
- Compute timing tuple F1 on labeled timing tables.
- Add regression suite for retrieval/extraction/validation.
- Measure manual effort reduction (time-to-first-driver) versus manual baseline.
- Run 1000+ page datasheet benchmarks and report SLO conformance.
- Add observability dashboards and failure triage runbook.

Exit criteria:
- Baseline PASS@K target met and reproducible.
- Median time-to-first-driver improves by at least 40% versus manual baseline.
- Large-datasheet SLO targets are met in benchmark runs.
- Failure categories are measurable and actionable.

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

Supporting metrics:
- Retrieval Recall@K on labeled query-page pairs.
- JSON validity rate from extractor.
- Validator catch rate for synthetic perturbations.
- Timing tuple F1 (`name`, `value`, `unit`, `condition`) on labeled pages.
- CoVe recovery rate after first fail.
- Median time-to-first-driver reduction versus manual workflow.
- Large-datasheet performance: indexing throughput (pages/min) and online p95 latency.
- UNCERTAIN rate and manual review turnaround.

Quality gates:
- No code synthesis from unvalidated JSON.
- Retry loop hard limit of 3.
- Timing outputs that fail validation are blocked or marked UNCERTAIN.
- Full provenance required for every emitted define.
- Release candidate must satisfy agreed SLO thresholds.

## Risks and Mitigations

- Risk: visually similar but wrong register pages retrieved.
  Mitigation: hybrid retrieval + RRF + hex-token boosting.

- Risk: VLM hallucinated addresses or bit fields.
  Mitigation: strict schema validation + SVD deterministic checks.

- Risk: timing table values extracted with wrong units or ambiguous conditions.
  Mitigation: unit normalization, monotonicity checks, and conflict detection before synthesis.

- Risk: silent propagation of wrong outputs.
  Mitigation: fail-closed behavior and UNCERTAIN routing.

## Immediate Next Steps

1. Add baseline datasheet and SVD datasets in `data/`.
2. Implement Stage 1-3 offline indexing first for a single MCU family.
3. Build retrieval eval set before tuning Stage 4 scoring.
4. Wire extraction, validation, and CoVe loop as a single orchestrated flow.
5. Add code synthesis only after validation pass path is stable.
6. Define manual-baseline measurement protocol and SLO benchmark harness for 1000+ page PDFs.
7. Add CI workflows under `.github/workflows/`.
