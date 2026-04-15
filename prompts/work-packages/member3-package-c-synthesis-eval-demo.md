# Prompt: Package C (Member 3) - Synthesis + Demo Core

Use this prompt when executing Package C.

## Prompt Text

You are responsible for Package C only: Synthesis + Demo Core.
Your job is to produce reliable driver artifacts and a credible demo package.
Work asynchronously using validated JSON fixtures first, then swap in Package B outputs.

Execution rule:
- Do one module at a time in strict order: C1 -> C2 -> C3.
- Do not advance until the current module has saved artifacts.

Objectives:
- Generate driver artifacts from validated JSON.
- Package a one-command demo, or deterministic replay if live E2E is unstable.

Modules:
- C1 Synthesis core: generate driver artifacts and provenance trace.
- C2 Demo package: create one-command demo or deterministic replay bundle.
- C3 Smoke check: run a quick dry run and write presenter notes.

Inputs:
- Validated JSON and validator reports from Package B when available.
- Use fixture JSON if upstream artifacts are delayed.

Required Outputs:
- driver.h
- driver.c
- audit_trace.json
- demo script or replay package
- smoke-run log and demo presenter notes

Hard Constraints:
- Never synthesize from unvalidated JSON.
- Keep provenance for every emitted symbol.
- Keep demo steps deterministic and quick to execute.

Definition of Done:
- Reproducible synthesis artifacts exist.
- Demo is runnable live or replayable from saved artifacts.

Scope note:
- Evaluation tables and taxonomy analysis are owned by Package A and Package B.

Per-module output checklist:
- C1 output: driver.h, driver.c, audit_trace.json.
- C2 output: demo command script or replay package with instructions.
- C3 output: smoke-run log and presenter notes.

Status Format:
- Current module:
- Scope completed:
- Open risk:
- Next exact command/action:
- Artifact paths produced:
