# KarcinoJen IEEE Draft Section Notes

This file provides section-wise content you can paste into an IEEE paper on Overleaf.

Important writing rule for submission quality:
- Do not invent results or citations.
- Keep all measured values from scripts and logs.
- Leave any unknown value as TBD until experiment scripts produce it.

## 1. Title Options

Option A:
- KarcinoJen: A Reliability-Centered Multimodal Pipeline for MCU Datasheet Register Extraction and Driver Synthesis

Option B:
- From Datasheet Pages to Verified Driver Code: Multimodal Retrieval, SVD Grounding, and CoVe Correction in KarcinoJen

Option C:
- Deterministic Validation over Multimodal Evidence: A Practical Architecture for MCU Register Extraction

Recommended final title style:
- Keep one technical keyword from each contribution axis: multimodal retrieval, deterministic validation, CoVe correction, driver synthesis.

## 2. Abstract Draft (150-220 words)

Embedded firmware development requires precise interpretation of hardware datasheets, where minor address or bit-field errors can cause severe functional faults. We present KarcinoJen, a reliability-centered pipeline that transforms natural-language register queries into validated C driver artifacts from datasheet evidence. The method combines multimodal retrieval using ColPali visual embeddings with lexical fusion, strict JSON extraction with a vision-language model, deterministic CMSIS-SVD validation, and a correction loop based on Chain-of-Verification (CoVe). Only validated facts are passed to code synthesis, producing driver.h, driver.c, and an audit trace linking generated symbols to evidence.

We evaluate on MCU-Bench, a curated dataset of 17 register queries across STM32F401 and RP2040 datasheets. The evaluation compares three configurations: Vanilla VLM, validation without CoVe, and full KarcinoJen. Primary metrics include PASS@K address accuracy, schema validity, CoVe recovery rate, and error-taxonomy distribution. Results show TBD improvements in PASS@K and TBD gains in extraction validity for full KarcinoJen over baseline variants. These findings suggest that deterministic grounding and correction loops are practical mechanisms for reducing hallucination-driven extraction failures in datasheet-centric code generation.

## 3. Index Terms

- Embedded Systems
- Hardware Datasheet Understanding
- Multimodal Retrieval
- Vision-Language Models
- Deterministic Validation
- Program Synthesis

## 4. Introduction (Draft Content)

### 4.1 Problem Context

Firmware engineers routinely parse long datasheets to identify register addresses, offsets, bit fields, and configuration semantics. Existing LLM-assisted workflows reduce writing effort but remain fragile when applied to hardware specifications, where numerical precision and table structure are critical.

### 4.2 Core Challenge

Two failure modes are dominant in this setting:
- Stochastic hallucination in address and bitfield outputs.
- Loss of structural signal when table-heavy pages are reduced to plain text retrieval.

### 4.3 Proposed Direction

KarcinoJen addresses these issues with a reliability-first architecture:
- Visual-first retrieval over rendered datasheet pages.
- Deterministic SVD-grounded validation before synthesis.
- CoVe-based correction loop under a strict retry budget.

### 4.4 Contributions (Use As Bullet List In Paper)

1. A stage-contracted architecture that enforces fail-closed progression from extraction to synthesis.
2. A practical combination of multimodal retrieval and deterministic symbolic validation for register extraction.
3. A correction workflow (CoVe) that injects mismatch reports into re-prompted extraction.
4. A reproducible evaluation protocol on MCU-Bench using PASS@K, validity, recovery, and taxonomy metrics.

## 5. Related Work (Section Guidance + Draft Text)

Structure this section as thematic clusters with evidence-backed comparison points.

### 5.1 LLM/VLM for Technical Document Understanding

Prior work shows strong language-level extraction ability but weaker robustness on high-precision numeric facts, particularly when documents contain dense tables, layout-specific semantics, and domain abbreviations.

### 5.2 RAG and Multimodal Retrieval

Text-only retrieval often under-represents diagram/table relationships. Multimodal retrieval methods preserve page-level visual semantics and can better localize table-based evidence. KarcinoJen follows this direction by combining ColPali late-interaction scoring with lexical retrieval fusion.

### 5.3 Program Synthesis with Verification

Code-generation pipelines increasingly include validators, but many stop at syntax or schema checks. KarcinoJen extends this idea with deterministic hardware-grounded checks using CMSIS-SVD, then only synthesizes from validated facts.

### 5.4 Positioning Statement

KarcinoJen is not a new foundation model; its novelty is architectural: deterministic grounding and correction over multimodal evidence under explicit stage contracts.

Citation placeholders to replace with your survey:
- [CITATION_RAG_MULTIMODAL]
- [CITATION_COLPALI_OR_LATE_INTERACTION]
- [CITATION_HARDWARE_CODEGEN]
- [CITATION_VERIFICATION_LOOP]

## 6. Methodology

### 6.1 Pipeline Overview

The end-to-end flow is:
- Datasheet page rendering (300 dpi images)
- ColPali page embedding and indexing
- Hybrid retrieval (MaxSim + lexical, fused by RRF)
- VLM extraction with strict JSON output
- SVD-based deterministic validation
- CoVe mismatch-guided correction (max 3 attempts)
- Driver synthesis and enrichment
- Metric computation and audit trace output

### 6.2 Retrieval Stage

Canonical retrieval uses ColPali visual embeddings with late interaction and lexical fusion:
- Semantic signal: visual multimodal page embeddings.
- Lexical signal: keyword overlap with hexadecimal token boost.
- Fusion: Reciprocal Rank Fusion.

Fallback profile:
- Lexical retrieval can be used as low-resource ablation.
- In fallback mode, top pages are still rendered to images for VLM extraction.

### 6.3 Extraction and Validation

Extraction uses a strict JSON schema for:
- peripheral
- register_name
- base_address
- offset
- bits
- optional timing_constraints

Validation checks include:
- Address range against CMSIS-SVD peripheral/register ground truth.
- Bit arithmetic constraints.
- Name fuzzy match.
- Optional timing consistency checks.

### 6.4 CoVe Loop

On validation failure, mismatch reports are fed back to extraction prompting. The retry cap is fixed at 3. If extraction remains invalid, the pipeline returns UNCERTAIN rather than synthesizing potentially unsafe outputs.

### 6.5 Synthesis and Traceability

Validated extraction is transformed to:
- driver.h
- driver.c
- audit_trace.json

PASS@K is computed by diffing generated register addresses against SVD-derived addresses.

## 7. Experimental Setup

### 7.1 Dataset

MCU-Bench v1.0:
- Total queries: 17
- MCU families: STM32F401, RP2040
- Each record includes natural-language query and ground-truth register JSON.

### 7.2 Configurations

Run the following configurations on identical query sets:
- B1: Vanilla VLM (no validation, no CoVe)
- B2: Validation enabled, CoVe disabled
- B3: Resource-constrained retrieval fallback (lexical)
- P: Full KarcinoJen (multimodal retrieval + validation + CoVe)

### 7.3 Models and Runtime (Fill Actual Versions)

- Retrieval model: vidore/colpali-v1.3-merged
- Primary VLM: Gemini 2.5 Flash
- Local VLM fallbacks: qwen2.5vl:7b, llava:latest
- Synthesis primary: Groq llama-3.3-70b-versatile
- Synthesis local fallback: qwen2.5:7b-instruct (Ollama)

### 7.4 Metrics

Primary:
- PASS@K (address accuracy)
- Extraction schema validity rate
- CoVe recovery rate
- Error taxonomy counts

Secondary:
- Runtime per query
- Failure mode distributions

## 8. Results and Analysis (Fill With Script Outputs)

### 8.1 Main Quantitative Table

Use this table in Overleaf:

| Configuration | PASS@K | Schema Validity | CoVe Recovery | Address Accuracy | Notes |
|---|---:|---:|---:|---:|---|
| B1 Vanilla VLM | TBD | TBD | N/A | TBD | No deterministic guardrails |
| B2 Validation w/o CoVe | TBD | TBD | 0 | TBD | Fail-closed without repair |
| B3 Lexical Fallback | TBD | TBD | TBD | TBD | Resource-constrained profile |
| P Full KarcinoJen | TBD | TBD | TBD | TBD | Proposed method |

### 8.2 Delta Table (Optional but Recommended)

| Comparison | PASS@K Delta | Validity Delta | Interpretation |
|---|---:|---:|---|
| P vs B1 | TBD | TBD | End-to-end reliability gain |
| P vs B2 | TBD | TBD | Added value from CoVe |
| P vs B3 | TBD | TBD | Added value from multimodal retrieval |

### 8.3 Suggested Narrative Template

- Full KarcinoJen improved PASS@K by TBD points over Vanilla VLM.
- Deterministic validation reduced invalid extractions by TBD points.
- CoVe recovered TBD percent of initially failing extractions.
- Remaining failures were primarily tied to provider availability/quota limits and not deterministic validation logic.

## 9. Qualitative Error Analysis

Provide 2-3 case studies with before/after correction snapshots.

Case format:
- Query: <text>
- Failure type: Address Drift or Layout Confusion or Context Bleed
- Initial extraction error: <details>
- Validator mismatch report: <details>
- CoVe correction outcome: recovered or unresolved
- Final output status: PASS or UNCERTAIN

Recommended error taxonomy presentation:

| Error Type | Count (B1) | Count (P) | Change |
|---|---:|---:|---:|
| Address Drift | TBD | TBD | TBD |
| Layout Confusion | TBD | TBD | TBD |
| Context Bleed | TBD | TBD | TBD |
| Uncategorized | TBD | TBD | TBD |

## 10. Threats to Validity

Internal validity:
- API availability and quota effects can influence extraction outcomes.
- Prompt quality may interact with model-specific decoding behavior.

Construct validity:
- PASS@K captures address correctness, but not all semantic quality dimensions.
- Some timing constraints may be sparse in selected benchmark queries.

External validity:
- Current benchmark includes 2 MCU families; generalization to wider vendor ecosystems requires expansion.
- Results may vary across datasheet layouts with different formatting conventions.

Conclusion validity:
- Keep confidence intervals or bootstrap estimates where possible.
- Report all failed runs and retried conditions transparently.

## 11. Reproducibility Checklist

Include a dedicated paragraph or appendix checklist:

- Code repository commit hash: TBD
- Config file snapshot: configs/model_config.json
- Dataset version: MCU-Bench v1.0 (17 records)
- Hardware runtime: GPU model + VRAM, OS, Python version
- Model identifiers and endpoint types
- Random seed policy and deterministic settings
- Script commands used for all tables/figures

Suggested command references:
- python scripts/run_experiment.py
- python scripts/run_tests.py
- python scripts/run_pipeline.py --datasheet ... --query ...

## 12. Conclusion and Future Work

KarcinoJen demonstrates that reliability-focused architecture, rather than model replacement alone, can materially improve datasheet-to-code pipelines. The combination of multimodal evidence retrieval, deterministic SVD grounding, and CoVe correction provides a practical mechanism for reducing extraction errors before synthesis. Future work will expand benchmark breadth, strengthen statistical reporting, and integrate broader MCU/vendor coverage with sustained reproducibility constraints.

## 13. Claims-to-Evidence Matrix (For Internal QA)

| Claim | Evidence Source |
|---|---|
| Full method improves address-level correctness | PASS@K from scripts/run_experiment.py outputs |
| Validation reduces hallucination propagation | B1 vs B2 failure distributions |
| CoVe recovers part of failed extractions | Recovery rates in full method logs |
| Architecture remains fail-closed | UNCERTAIN outputs when extraction fails after retry cap |

## 14. Overleaf Mapping Notes

Use these section commands in IEEEtran:
- Abstract -> abstract environment
- Index Terms -> IEEEkeywords environment
- Introduction -> section I
- Related Work -> section II
- Methodology -> section III
- Experimental Setup -> section IV
- Results and Analysis -> section V
- Qualitative Error Analysis -> section VI
- Threats to Validity -> section VII
- Conclusion -> section VIII

Figure recommendations:
- Fig. 1: End-to-end architecture flow diagram
- Fig. 2: CoVe correction loop detail
- Fig. 3: Example retrieval evidence pages and extracted JSON snippet

Table recommendations:
- Tbl. 1: Configuration and model settings
- Tbl. 2: Main quantitative results
- Tbl. 3: Error taxonomy comparison

## 15. Final Pre-Submission Checks

- Replace all TBD entries with script-generated values.
- Ensure each numeric claim appears in one table/figure.
- Ensure no claim relies on anecdotal outputs only.
- Keep fallback/ablation language separate from canonical architecture claims.
- Ensure terminology is consistent: KarcinoJen, CoVe, PASS@K, MCU-Bench.
