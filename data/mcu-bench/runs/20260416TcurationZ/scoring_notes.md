# Scoring Notes (Draft)

Run ID: 20260416TcurationZ

Mode: retrieval_proxy_only (validated/synthesis artifacts not present)

What is measured:
- PASS@K proxy using whether expected benchmark page appears in retrieval top-K.

What is not measured yet:
- Address-level correctness of synthesized code against SVD.
- CoVe-corrected extraction quality from Package B.

Upgrade path when upstream artifacts arrive:
1. Map each benchmark ID to validated JSON and synthesis outputs.
2. Compute true PASS@K using generated addresses versus SVD ground truth.
3. Keep this draft as historical baseline in paper appendix.
