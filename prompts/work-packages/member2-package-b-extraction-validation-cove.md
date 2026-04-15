# Prompt: Package B (Member 2) - Extraction + Validation + CoVe Core

Use this prompt when executing Package B.

## Prompt Text

You are responsible for Package B only: Extraction + Validation + CoVe Core.
Your job is to maximize correctness and reliability for structured extraction.
Work asynchronously and continue with fixtures if Package A outputs are delayed.

Execution rule:
- Do one module at a time in strict order: B1 -> B2 -> B3 -> B4 -> B5.
- Move to the next module only when current module done check passes.

Objectives:
- Engineer strict extraction prompts for schema-valid JSON.
- Implement deterministic validation checks against SVD.
- Implement CoVe retry loop with maximum 3 attempts.
- Build paper-ready qualitative error taxonomy evidence.

Modules:
- B1 Baseline extraction: create prompt v1 and schema harness.
- B2 Prompt tuning: iterate prompts to raise schema validity.
- B3 Deterministic validation: implement checks and mismatch reports.
- B4 CoVe loop: run retries with max 3 attempts and UNCERTAIN fallback.
- B5 Error analysis: label failures into taxonomy categories with evidence snippets.

Inputs:
- Query and page input from Package A when available.
- Otherwise use synthetic retrieval fixtures and continue.

Required Outputs:
- Extraction prompt versions and run notes.
- Schema-valid extracted JSON artifacts.
- Validator mismatch reports.
- CoVe retry logs and final corrected JSON or UNCERTAIN.
- Error taxonomy evidence pack (Address Drift, Layout Confusion, Context Bleed).

Hard Constraints:
- Never bypass validation.
- Retry cap is 3 attempts.
- Emit UNCERTAIN when correction does not converge.
- Preserve structured logs for paper evidence.

Definition of Done:
- At least 80 percent schema-valid outputs on the target sample set.
- Validator catches injected address/bit errors.
- Retry loop behavior is deterministic and auditable.
- Taxonomy evidence pack is ready for paper qualitative section.

Per-module output checklist:
- B1 output: prompt v1 plus extraction/parsing run log.
- B2 output: prompt iteration notes plus schema-valid JSON set.
- B3 output: validator mismatch reports on fail injections.
- B4 output: retry logs and corrected JSON or UNCERTAIN outcomes.
- B5 output: categorized failure table and supporting evidence snippets.

Status Format:
- Current module:
- Scope completed:
- Open risk:
- Next exact command/action:
- Artifact paths produced:
