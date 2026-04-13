# Work Split and Git Collaboration Plan (3 Members)

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
| Timing constraint extraction and normalization | Member 2 | Member 1 |
| Timing consistency validation policy | Member 2 | Member 3 |
| Large-datasheet performance benchmarking | Member 1 | Member 3 |
| Manual effort KPI benchmarking | Member 3 | Member 2 |
| CI/CD and release process | Member 3 | Member 1 |

## Deliverables Per Member

### Member 1 (Indexing + Retrieval)
Deliverables:
- `src/ingest/` PDF page renderer at 300 dpi.
- `src/index/` ColPali embedding pipeline.
- `src/retrieval/` MaxSim and BM25+hex boost retrieval.
- ChromaDB schema and index maintenance scripts.
- 1000+ page indexing/retrieval benchmark harness and SLO reports.

Done criteria:
- Datasheet indexing reproducible.
- Top-k retrieval quality baseline achieved on labeled queries.
- Throughput and retrieval latency meet agreed SLO targets on benchmark dataset.

### Member 2 (Extraction + Validation)
Deliverables:
- `src/extractor/` strict JSON extraction prompt and adapters.
- `schemas/timing_constraints.schema.json` and extractor support for timing tuples.
- `src/validator/` deterministic SVD checks.
- Deterministic timing checks (unit normalization, monotonicity, conflict detection).
- CoVe correction loop implementation with max 3 retries.
- Structured mismatch reporting and retry telemetry.

Done criteria:
- High JSON schema validity rate.
- Validator catches synthetic error injections reliably.
- Timing tuple extraction reaches agreed F1 on labeled timing tables.
- Retry loop converges or exits with UNCERTAIN.

### Member 3 (Synthesis + QA + Integration)
Deliverables:
- `src/synthesis/` code generation for `driver.h` and `driver.c`.
- `audit_trace.json` generation with per-symbol provenance.
- `src/orchestration/` pipeline integration flow.
- `tests/` integration/regression suites and PASS@K runner.
- Timing validation to synthesis gating and uncertainty routing tests.
- Manual effort KPI study harness (`time-to-first-driver`) and reporting dashboard.
- CI pipeline, release tags, and changelog workflow.

Done criteria:
- Generated code compiles for baseline targets.
- PASS@K and trace completeness reports available in CI.
- Median `time-to-first-driver` reduction is reported and tracked per release.

## Sprint-Oriented Work Plan

### Sprint 1
- Member 1: Stage 1-3 baseline indexing for one MCU datasheet.
- Member 2: JSON schema and extractor prompt contract.
- Member 3: Repo scaffolding, CI skeleton, test harness.

### Sprint 2
- Member 1: Stage 4 hybrid retrieval and RRF fusion.
- Member 2: Stage 5 extraction service, timing tuple schema, and schema enforcement.
- Member 3: Integration tests for retrieval to extraction handoff.

### Sprint 3
- Member 2: Stage 6 validator (register + timing checks) and Stage 7 CoVe loop.
- Member 1: Retrieval tuning for failure cases from validator feedback.
- Member 3: Stage 8 synthesis and audit trace implementation.

### Sprint 4
- Member 3: Stage 9 PASS@K evaluator and release pipeline.
- Member 1: 1000+ page performance benchmark and SLO conformance report.
- Member 2: timing extraction quality benchmark and defect burn-down.
- Member 3: manual-effort KPI baseline study and release report integration.
- All: benchmark report and documentation freeze.

## Git Work Split

## Branching Model

- `main`: protected, release-ready only.
- `develop`: integration branch for ongoing sprint work.
- Feature branches: one per task and owner.

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
- Performance/SLO evidence for changes affecting indexing, retrieval, or extraction latency.
- Risk note and rollback note.
- Updated docs if interface changed.

## Integration Cadence

- Daily: members rebase feature branches on `develop`.
- Twice weekly: integration cut on `develop` with full test run.
- End of sprint: release candidate from `develop` to `main` via PR.

## Conflict Avoidance Rules

- One owner merges first for shared contracts (`schemas/`, shared interfaces).
- Use schema versioning for extractor-validator-synthesis contracts.
- Any breaking interface change requires joint approval from affected owners.

## Escalation and Fallback

- If CoVe still fails after 3 tries, mark output `UNCERTAIN` and open review ticket.
- Critical bug in `main` is fixed via `hotfix/<topic>` and back-merged to `develop`.
