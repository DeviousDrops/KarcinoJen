# KarcinoJen Implementation Plan V2 (Publication Track)

## 1. Objective

Deliver a submission-ready research package that demonstrates a publishable contribution:
- Multimodal-first retrieval for datasheet understanding
- Deterministic validation and CoVe correction for reliability
- Traceable code synthesis from validated facts

This plan is separate from the earlier short sprint plan and is focused on publication quality.

## 2. Success Criteria

Technical criteria:
- End-to-end pipeline runs reproducibly on at least two MCU families.
- Full experiment suite runs for all baselines and proposed method.
- Metrics are generated from scripts, not manual edits.

Research criteria:
- Clear novelty statement and contribution boundaries.
- Fair baseline comparisons and ablations.
- Explicit threats to validity and limitations.

Artifact criteria:
- Clean experiment logs and config snapshots.
- Paper-ready tables and figure assets.
- Reproducibility appendix and runbook.

## 3. Workstreams

WS1. System Stability and Reproducibility
- Freeze runtime profiles (canonical and fallback).
- Freeze model versions and config files.
- Add reproducible run manifests for every experiment.

WS2. Benchmark and Ground Truth Quality
- Finalize MCU-Bench scope and labeling protocol.
- Validate ground truth consistency across queries.
- Add query stratification by difficulty and peripheral type.

WS3. Experiments and Analysis
- Run baselines and full method on identical splits.
- Compute PASS@K, validity, CoVe recovery, and taxonomy metrics.
- Perform ablations: retrieval backend, CoVe on/off, validation on/off.

WS4. Writing and Packaging
- Draft IEEE manuscript from verified evidence only.
- Add architecture figure, flow diagram, and results tables.
- Prepare submission checklist and final artifact bundle.

## 4. Timeline (6 Weeks)

### Week 1: Freeze Core Setup
Deliverables:
- Frozen configs and model selection policy
- Canonical Colab runbook and local fallback runbook
- Reproducibility manifest template

Exit gate:
- One canonical run and one fallback run produce equivalent stage logs format.

### Week 2: Benchmark Finalization
Deliverables:
- Final MCU-Bench query list and metadata
- Ground-truth QA report
- Difficulty tiers and split policy

Exit gate:
- Benchmark version is immutable for experiment phase.

### Week 3: Baseline and Ablation Runs
Deliverables:
- Baseline 1, Baseline 2, and fallback-ablation outputs
- Raw metrics exports and failure traces

Exit gate:
- All baseline runs completed with consistent seeds and configs.

### Week 4: Full Method Runs
Deliverables:
- Full KarcinoJen experiment outputs
- CoVe recovery analysis and taxonomy summary
- PASS@K comparison table

Exit gate:
- Primary quantitative claims are supported by script-generated outputs.

### Week 5: Paper Drafting and Internal Review
Deliverables:
- Full IEEE draft v1
- Claims-to-evidence matrix
- Reviewer-style internal critique and revision log

Exit gate:
- No unsupported claim remains in draft.

### Week 6: Final Hardening and Submission Package
Deliverables:
- Final manuscript
- Reproducibility appendix
- Camera-ready figures/tables and artifact archive

Exit gate:
- Submission checklist fully satisfied.

## 5. Baseline Matrix To Run

Required configurations:
- B1: Vanilla VLM (no deterministic validator, no CoVe)
- B2: Validation enabled, CoVe disabled
- B3: Resource-constrained retrieval fallback (lexical)
- P: Full KarcinoJen (multimodal retrieval + validation + CoVe)

Required metrics:
- PASS@K
- Schema validity rate
- SVD validation pass rate
- CoVe recovery rate
- Error taxonomy counts

## 6. Writing Plan

Paper sections and ownership:
- Introduction + Related Work: novelty positioning and gap statement
- Methodology: stage contracts and architecture rationale
- Experiments: setup, baselines, fairness controls
- Results: quantitative + qualitative findings
- Threats and limitations: explicit and honest scope boundaries

## 7. Risks and Mitigations

Risk: weak novelty perception
Mitigation: frame novelty as reliability architecture and deterministic grounding, not model invention.

Risk: baseline fairness challenges
Mitigation: run all baselines on same split, same prompts where applicable, same metrics.

Risk: limited benchmark size
Mitigation: include confidence intervals or bootstrap estimates and clearly bound claims.

Risk: reproducibility gaps
Mitigation: lock configs, keep manifests, publish scripts and run instructions.

## 8. Definition Of Done

The project is submission-ready when:
- Every major claim is traceable to an artifact.
- Every reported metric can be regenerated.
- Baseline and ablation comparisons are complete.
- Limitations are explicitly documented.
- Draft quality passes internal reviewer checklist.