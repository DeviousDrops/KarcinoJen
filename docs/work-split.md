# 3-Person Work Package Assignment (Async, No Split)

## Objective

This plan assigns exactly one complete work package to each member.
Packages are selected by difficulty and expected time consumption.
Each member can work asynchronously at any time without splitting ownership.

## Working Rules

- One owner per package, end-to-end responsibility.
- No package-level co-ownership; collaboration happens through artifact handoffs.
- If an upstream artifact is missing, use mock fixtures and continue.
- Keep progress in short reproducible runs (1 to 3 hours each).
- Prioritize prompt engineering and paper evidence over feature breadth.

## One Package Per Member

| Package | Owner | Difficulty | Estimated Time | Final Package Output |
|---|---|---|---|---|
| Package A: Data + Retrieval + Scoring Core | Member 1 | High | 12 to 14 hours | Benchmark set, retrieval top-k logs, and PASS@K summary draft |
| Package B: Extraction + Validation + Error Analysis Core | Member 2 | High | 13 to 15 hours | Validator-passing JSON, CoVe retry logs, and taxonomy evidence |
| Package C: Synthesis + Demo Core | Member 3 | Low-Medium | 6 to 8 hours | Driver artifacts and demo flow |

## Modular Breakdown: Member 1 (Package A)

Do modules in order:

| Module | Task | Estimated Time | Input | Output | Done Check |
|---|---|---|---|---|---|
| A1 | Freeze benchmark scope and IDs | 2h | Query ideas and datasheet page refs | Stable benchmark ID list | 10 to 20 benchmark items locked |
| A2 | Build query and ground-truth skeleton files | 3h | A1 IDs | `data/mcu-bench/queries.jsonl`, skeleton `ground_truth.jsonl` | Every benchmark item has query text and metadata |
| A3 | Run retrieval and collect top-k logs | 4h | A2 files and page assets or placeholders | Top-k retrieval logs per query | All benchmark queries return top-k results |
| A4 | Freeze retrieval config and rerun manifest | 2h | A3 logs | Retrieval config notes and run manifest | Package A retrieval runs are reproducible |
| A5 | Build scoring bundle and PASS@K summary draft | 1 to 3h | A4 outputs + validated/synthesis artifacts | PASS@K summary csv/json and scoring notes | Paper table ingestion is ready from Package A outputs |

## Modular Breakdown: Member 2 (Package B)

Do modules in order:

| Module | Task | Estimated Time | Input | Output | Done Check |
|---|---|---|---|---|---|
| B1 | Create extraction prompt v1 and schema harness | 3h | Sample page-query pairs | Prompt v1 and parser/check logs | End-to-end extraction run completes |
| B2 | Iterate extraction prompts for validity | 4h | B1 baseline outputs | Prompt v2+ notes and JSON outputs | >=80 percent schema-valid JSON on sample set |
| B3 | Implement validator checks and mismatch report | 3h | B2 JSON and SVD files | Deterministic validator reports | Injected address/bit errors are detected |
| B4 | Add CoVe retry loop with stop rules | 2 to 3h | B3 mismatch reports | Retry logs and final JSON or UNCERTAIN | Max 3 retries, deterministic fail-closed behavior |
| B5 | Build qualitative error taxonomy evidence pack | 1 to 2h | B3/B4 failures and corrections | Address Drift, Layout Confusion, Context Bleed examples | Taxonomy table and evidence snippets are paper-ready |

## Modular Breakdown: Member 3 (Package C)

Do modules in order:

| Module | Task | Estimated Time | Input | Output | Done Check |
|---|---|---|---|---|---|
| C1 | Build synthesis templates and trace mapping | 2 to 3h | Validated JSON fixtures | `driver.h`, `driver.c`, `audit_trace.json` | Every emitted symbol has provenance |
| C2 | Package demo flow or replay bundle | 2h | C1 artifacts + sample query inputs | Demo script or deterministic replay package | One-command showable demo path exists |
| C3 | Run smoke check and handoff demo notes | 1 to 2h | C2 package | Smoke-run log and presenter notes | Demo can be shown quickly without setup surprises |

## Async Dependency Contracts

- Member 1 hands off A2 and A3 artifacts to unblock B1/B2 realism.
- Member 2 can start B1/B2 with fixtures, then replace inputs when A3 is ready.
- Member 2 hands off B4 validated JSON outputs to unblock C1.
- Member 3 hands off C1 synthesis outputs to Member 1 for A5 scoring summary.
- Member 2 hands off B5 taxonomy evidence for final paper write-up.
- Handshake files are versioned so members do not need live coordination.

## Prompt Assets Per Package

Prompt files are stored under `prompts/work-packages/`:

- `member1-package-a-data-retrieval.md`
- `member2-package-b-extraction-validation-cove.md`
- `member3-package-c-synthesis-eval-demo.md`

Each member owns and iterates only their package prompt file.

## Two-Day Execution Plan

### Day 1 (Build Package Cores)

- Member 1: complete A1 and A2, start A3.
- Member 2: complete B1 and most of B2.
- Member 3: complete C1.

Day 1 exit criteria:
- Every member completes at least two modules with reproducible artifacts.

### Day 2 (Finalize for Paper + Demo)

- Member 1: finish A3, A4, and A5.
- Member 2: finish B2, B3, B4, and B5.
- Member 3: finish C2 and C3.

Day 2 exit criteria:
- All module checkboxes are done, with Package A/B paper evidence and Package C demo assets present.

## Demo Strategy When "Nothing to Show"

If full live E2E is unstable, show a minimal but credible flow:

- One benchmark query and retrieved pages.
- JSON before and after validator/CoVe.
- Generated `driver.h`/`driver.c` with `audit_trace.json`.
- One PASS@K snapshot plus one qualitative correction case.

## Git Workflow (No Split Ownership)

Branch model:
- `main`: paper/demo stable.
- `feat/m1-package-a-<topic>` for Package A changes.
- `feat/m2-package-b-<topic>` for Package B changes.
- `feat/m3-package-c-<topic>` for Package C changes.
- `exp/<topic>` for temporary prompt experiments.

Merge rule:
- Package owner merges only after package done criteria and artifacts are present.
- Every metrics-affecting merge includes run manifest evidence.

## Session Checklist

For each member session:

1. Pick the next unfinished module in your package sequence.
2. Run the minimum commands needed to produce one artifact.
3. Save outputs in timestamped run folders.
4. Record prompt version and observed metrics.
5. Commit reproducible progress.

## Risk Controls

- CoVe retry loop hard limit is 3; otherwise emit `UNCERTAIN`.
- Never synthesize code from unvalidated JSON.
- If retrieval quality drops, narrow benchmark scope before tuning more components.
- If time is short, prioritize one strong ablation and one qualitative error case for paper evidence.
