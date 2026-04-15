# Prompt: Package A (Member 1) - Data + Retrieval Core

Use this prompt when executing Package A.

## Prompt Text

You are responsible for Package A only: Data + Retrieval Core.
Your job is to deliver benchmark curation and retrieval outputs for a 2-day paper-first sprint.
Work asynchronously and do not wait for other packages.

Execution rule:
- Do one module at a time in strict order: A1 -> A2 -> A3 -> A4 -> A5.
- Do not start a later module before finishing the current module done check.

Objectives:
- Freeze a compact benchmark set (10 to 20 items).
- Produce retrieval top-k outputs for every benchmark query.
- Record retrieval configuration and run manifests so results are reproducible.
- Build scoring summaries (PASS@K draft artifacts) for paper ingestion.

Modules:
- A1 Scope freeze: lock benchmark IDs and page references.
- A2 Dataset skeleton: write queries and ground-truth skeleton files.
- A3 Retrieval run: generate top-k logs for each query.
- A4 Repro freeze: save retrieval config and final run manifest.
- A5 Scoring draft: generate PASS@K summary artifacts from available validated/synthesis outputs.

Inputs:
- Datasheet PDFs and page references when available.
- If missing, create placeholder page IDs and continue with fixtures.
- Consume validated JSON/synthesis artifacts when available for A5 scoring.

Required Outputs:
- data/mcu-bench/queries.jsonl
- data/mcu-bench/ground_truth.jsonl (skeleton allowed if annotation is incomplete)
- retrieval run logs (top-k per query)
- retrieval configuration notes and run manifest
- PASS@K summary draft (csv/json) and scoring notes

Hard Constraints:
- Keep artifacts machine-readable.
- Keep every run reproducible with timestamped output folders.
- Do not change extraction, validation, or synthesis logic.

Definition of Done:
- Every benchmark query has a top-k retrieval result.
- Run manifest is saved and sufficient for rerun.
- Outputs are ready for Package B and Package C consumption.
- PASS@K draft artifacts are ready for paper table assembly.

Per-module output checklist:
- A1 output: benchmark ID manifest.
- A2 output: queries.jsonl and ground_truth.jsonl skeleton.
- A3 output: top-k retrieval logs.
- A4 output: frozen retrieval config and run manifest.
- A5 output: PASS@K summary draft and scoring run notes.

Status Format:
- Current module:
- Scope completed:
- Open risk:
- Next exact command/action:
- Artifact paths produced:
