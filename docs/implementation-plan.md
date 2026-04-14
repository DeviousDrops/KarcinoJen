# KarcinoJen

## Implementation Plan

KarcinoJen is a demo-first research prototype that generates verifiable C driver snippets from vendor MCU datasheet PDFs using a visual-first RAG pipeline and deterministic CMSIS-SVD checks.

## Project Goal

Create an end-to-end system that:
- Ingests raw datasheet PDFs without OCR.
- Retrieves relevant register pages using visual and lexical hybrid retrieval.
- Extracts register definitions (and optional timing constraints) with a VLM into strict JSON.
- Validates core register facts against CMSIS-SVD with deterministic checks.
- Synthesizes traceable C driver artifacts for a limited demo query set.

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

## One-Week Demo Timeline

### Day 1: Dataset and Wiring
Tasks:
- Select one MCU family and 1 to 2 datasheets.
- Add matching CMSIS-SVD files.
- Confirm schema contracts and run a minimal dry run.

Exit criteria:
- One datasheet and one SVD pair run through a smoke pipeline.

### Day 2: Offline Ingestion and Visual Index
Tasks:
- Implement PDF page rendering at 300 dpi.
- Generate ColPali patch embeddings.
- Store page entries in ChromaDB with metadata.

Exit criteria:
- Selected datasheets are indexed and queryable.

### Day 3: Hybrid Retrieval
Tasks:
- Implement MaxSim late interaction.
- Implement BM25 with hex token boost.
- Fuse with Reciprocal Rank Fusion.

Exit criteria:
- Retrieval returns top-k pages for a curated query list.

### Day 4: VLM Extraction
Tasks:
- Add strict JSON extraction prompt.
- Add parser and schema validation.
- Support one open model path and one benchmark path.

Exit criteria:
- Extractor returns schema-valid JSON on most curated samples.

### Day 5: Validation and Re-prompt Loop
Tasks:
- Implement address, bit-field, and fuzzy-name checks.
- Add mismatch report format.
- Add CoVe retry loop up to 3 attempts.

Exit criteria:
- Invalid outputs are rejected with explicit mismatch reports.

### Day 6: Code Synthesis and Demo Script
Tasks:
- Generate driver.h, driver.c, and audit_trace.json from validated JSON.
- Build a single command demo flow for end-to-end run.

Exit criteria:
- End-to-end run succeeds on selected demo queries.

### Day 7: Evaluation and Paper Assets
Tasks:
- Compute PASS@K on curated benchmark set.
- Collect qualitative error analysis examples.
- Finalize figures/tables and reproducibility notes for the paper.

Exit criteria:
- Demo results and artifacts are ready for publication submission.

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
- Validator catch rate on curated fail cases.
- CoVe recovery rate after first fail.
- Demo completion rate over target query set.

Quality gates:
- No code synthesis from unvalidated JSON.
- Retry loop hard limit of 3.
- Full provenance required for every emitted define.
- End-to-end demo must run reproducibly on one machine.

## Risks and Mitigations

- Risk: visually similar but wrong register pages retrieved.
  Mitigation: hybrid retrieval + RRF + hex-token boosting.

- Risk: VLM hallucinated addresses or bit fields.
  Mitigation: strict schema validation + SVD deterministic checks.

- Risk: timing table values extracted with wrong units or ambiguous conditions.
  Mitigation: unit normalization, monotonicity checks, and conflict detection before synthesis.

- Risk: one-week schedule cannot support full production hardening.
  Mitigation: prioritize a narrow demo query set and document known limitations.

- Risk: silent propagation of wrong outputs.
  Mitigation: fail-closed behavior and UNCERTAIN routing.

## Immediate Next Steps

1. Freeze a narrow benchmark set (10 to 20 queries) for one MCU family.
2. Implement Stage 1-4 quickly and start collecting intermediate outputs.
3. Add Stage 6-7 validation loop before widening query coverage.
4. Keep Stage 8 synthesis minimal and deterministic for paper demonstration.
5. Prepare paper-ready tables for PASS@K, recovery rate, and failure examples.
