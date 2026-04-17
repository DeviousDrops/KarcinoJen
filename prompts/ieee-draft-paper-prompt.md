
# IEEE Draft Paper Prompt (KarcinoJen)

Use this prompt to generate a full IEEE-style first draft from project artifacts.

## How To Use

1. Collect and paste the required inputs below.
2. Keep all measured numbers exactly as reported in your logs.
3. If a value is unknown, leave it as `TBD` and do not invent data.
4. Run the prompt in your writing model and iterate section-by-section.

## Required Inputs

- Project title candidate
- Target venue (workshop, conference, journal)
- Problem statement and motivation
- Final architecture summary
- Experiment setup (datasets, baselines, metrics)
- Result tables (PASS@K, validity, recovery, error taxonomy)
- Qualitative examples (failure and correction)
- Threats to validity and limitations
- Reproducibility details (models, versions, configs, seeds)

## Copy-Paste Prompt

You are a senior IEEE technical writer and research editor.
Write an IEEE-style draft paper for the following project:

Project: KarcinoJen
Domain: MCU datasheet understanding and driver generation
Core method: Multimodal retrieval (ColPali + lexical fusion) -> VLM extraction from page images -> deterministic SVD validation -> CoVe correction loop -> text-LLM synthesis and enrichment

Use the input package below as the only source of truth.
Do not fabricate results, citations, or numeric claims.
If data is missing, write `TBD` placeholders and explicitly list what is missing.

Input package:
[PASTE PROJECT INPUTS HERE]

Write the paper in this exact structure:
1. Title
2. Abstract (150 to 220 words)
3. Index Terms
4. Introduction
5. Related Work
6. Methodology
7. Experimental Setup
8. Results and Analysis
9. Qualitative Error Analysis
10. Threats to Validity
11. Reproducibility Checklist
12. Conclusion and Future Work

Style constraints:
- IEEE tone: precise, neutral, evidence-based.
- No marketing language.
- Every claim must map to a method detail or reported result.
- Distinguish clearly between canonical architecture and fallback/ablation profile.
- Explain why multimodal retrieval is required before VLM extraction.

Output requirements:
- Provide the full draft text with clear section headers.
- After the draft, provide a "Claims-to-Evidence Table" with two columns: claim and supporting evidence.
- After that, provide a "Missing Evidence" list with concrete experiments needed before submission.

Quality checks before finalizing:
- No fabricated numbers.
- No unsupported novelty claims.
- Consistent terminology across all sections.
- Explicit limitations section included.

## Fast Revision Prompt (Optional)

Use this after your first draft:

"Act as a strict IEEE reviewer. Critique the draft for novelty clarity, baseline fairness, reproducibility, and threats to validity. Return:
1) top 10 risks to rejection,
2) exact text edits to fix each risk,
3) an updated abstract and contributions list."