# Work Split and Git Plan for One-Week Demo (3 Members)

## Team Structure

- Member 1: Visual indexing and retrieval lead
- Member 2: Extraction and validation lead
- Member 3: Synthesis, QA, and integration lead

## Responsibility Matrix

| Area | Primary Owner | Secondary Owner |
|---|---|---|
| Stage 1 PDF rendering | Member 1 | Member 3 |
| Stage 2 ColPali embeddings | Member 1 | Member 2 |
| Stage 3 ChromaDB indexing | Member 1 | Member 3 |
| Stage 4 Hybrid retrieval | Member 1 | Member 2 |
| Stage 5 VLM extraction | Member 2 | Member 1 |
| Stage 6 SVD validator | Member 2 | Member 3 |
| Stage 7 CoVe retry loop | Member 2 | Member 3 |
| Stage 8 Code synthesis agent | Member 3 | Member 2 |
| Stage 9 PASS@K evaluation | Member 3 | Member 1 |
| Demo benchmark query set and labeling | Member 3 | Member 1 |
| CI sanity checks (minimal) | Member 3 | Member 1 |

## Deliverables Per Member

### Member 1 (Indexing + Retrieval)
Deliverables:
- `src/ingest/` PDF page renderer at 300 dpi.
- `src/index/` ColPali embedding pipeline.
- `src/retrieval/` MaxSim and BM25+hex boost retrieval.
- ChromaDB schema and index maintenance scripts.
- Quick benchmark harness for selected demo queries.

Done criteria:
- Datasheet indexing reproducible.
- Top-k retrieval quality baseline achieved on labeled queries.
- Retrieval works reliably on the curated demo query set.

### Member 2 (Extraction + Validation)
Deliverables:
- `src/extractor/` strict JSON extraction prompt and adapters.
- `src/validator/` deterministic SVD checks.
- CoVe correction loop implementation with max 3 retries.
- Structured mismatch reporting and retry telemetry.

Done criteria:
- High JSON schema validity rate.
- Validator catches synthetic error injections reliably.
- Retry loop converges or exits with UNCERTAIN.

### Member 3 (Synthesis + QA + Integration)
Deliverables:
- `src/synthesis/` code generation for `driver.h` and `driver.c`.
- `audit_trace.json` generation with per-symbol provenance.
- `src/orchestration/` pipeline integration flow.
- `tests/` integration/regression smoke tests and PASS@K runner.
- Demo scripts and paper-ready result tables.
- Minimal CI checks for lint/tests.

Done criteria:
- Generated code compiles for baseline targets.
- PASS@K and trace completeness reports available in CI.
- Demo run can be reproduced by another team member in one command flow.

## Day-Wise Work Plan (One Week)

### Day 1
- Member 1: Stage 1-3 baseline indexing for one MCU datasheet.
- Member 2: JSON schema and extractor prompt contract.
- Member 3: Curate benchmark query list and expected outputs format.

### Day 2
- Member 1: Stage 4 hybrid retrieval and RRF fusion.
- Member 2: Stage 5 extraction service and schema enforcement.
- Member 3: Build smoke tests for retrieval to extraction handoff.

### Day 3
- Member 2: Stage 6 validator and Stage 7 CoVe loop.
- Member 1: Retrieval tuning for failure cases from validator feedback.
- Member 3: Stage 8 synthesis skeleton and audit trace format.

### Day 4
- Member 1: stabilize indexing/retrieval path.
- Member 2: stabilize validator/retry path.
- Member 3: integrate end-to-end pipeline and run first full demo.

### Day 5
- All: fix top failure modes and finalize curated benchmark runs.

### Day 6
- Member 3: run PASS@K and produce result tables.
- Member 1 and Member 2: collect qualitative examples for paper narrative.

### Day 7
- All: freeze code, finalize docs, and package reproducibility notes.

## Git Work Split

## Branching Model

- `main`: protected, demo-stable only.
- Feature branches: short-lived branches per task.

Branch naming:
- `feat/m1-index-<topic>` for Member 1.
- `feat/m2-extract-<topic>` for Member 2.
- `feat/m3-synth-<topic>` for Member 3.
- `fix/<area>-<topic>` for cross-cutting fixes.

## Directory Ownership for PR Routing

- Member 1 owns: `src/ingest/`, `src/index/`, `src/retrieval/`.
- Member 2 owns: `src/extractor/`, `src/validator/`, `schemas/timing_constraints.schema.json`.
- Member 3 owns: `src/synthesis/`, `src/orchestration/`, `tests/`, `.github/`.

PR rules:
- At least 1 reviewer required.
- If code touches another member's primary area, that member must review.
- No direct push to `main`.
- Squash merge to keep history clean.

## Commit and PR Conventions

Commit format:
- `feat(index): add colpali batch encoder`
- `feat(validator): add bit overlap check`
- `fix(retrieval): correct hex token boost`
- `test(integration): add svd mismatch regression`

PR template checklist:
- Linked issue/task ID.
- Test evidence (unit/integration logs).
- Risk note and rollback note.
- Updated docs if interface changed.

## Integration Cadence (Demo)

- Daily: each member merges at least one completed task branch to `main` after review.
- End of week: freeze repository and tag demo snapshot.

## Conflict Avoidance Rules

- One owner merges first for shared contracts (`schemas/`, shared interfaces).
- Use schema versioning for extractor-validator-synthesis contracts.
- Any breaking interface change requires joint approval from affected owners.

## Escalation and Fallback

- If CoVe still fails after 3 tries, mark output `UNCERTAIN` and open review ticket.
- Critical bug in `main` is fixed via `hotfix/<topic>` and merged directly after review.
