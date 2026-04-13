# Architecture

## 1. System Intent

KarcinoJen is a visual-first register and timing extraction architecture that converts MCU datasheet pages into validated, traceable C driver artifacts.

Core principles:
- No OCR dependency. Datasheets are processed as images.
- Retrieval combines semantic visual matching and lexical precision.
- Validation is deterministic and SVD-grounded.
- Timing constraints are extracted as typed tuples and validated with deterministic rules.
- Generation is fail-closed: no unvalidated data reaches code synthesis.
- Every generated symbol is provenance-traceable.

## 2. End-to-End Dataflow

1. PDF datasheet pages are rendered to 300 dpi images.
2. ColPali produces patch-level 128-d embeddings per page.
3. ChromaDB stores per-page multi-vector embeddings, page image blob, and metadata.
4. Query-time hybrid retrieval runs late interaction and BM25 in parallel.
5. Top-k page images are sent to a VLM with strict JSON extraction prompt for register and timing facts.
6. Extracted JSON is validated against CMSIS-SVD checks plus deterministic timing checks.
7. Failures trigger grounded CoVe re-prompt with exact mismatch context (max 3 tries).
8. Validated JSON feeds a synthesis node that generates C files and audit trace.
9. PASS@K, timing tuple F1, and effort reduction metrics are computed for evaluation.

## 3. Stage Contracts

### Stage 1: PDF Datasheet Input (offline)
Input:
- Vendor PDF datasheet.

Processing:
- Render each page at 300 dpi into image format (PNG/JPEG).

Output:
- `PageImage[]` where each item includes source file and page number.

### Stage 2: ColPali Visual Indexer (offline)
Input:
- `PageImage`.

Processing:
- Split image into patches through ColPali.
- Emit one 128-d embedding per patch.

Output:
- `PageEmbeddingSet` (variable-length multi-vector per page).

### Stage 3: ChromaDB Visual Index (offline)
Input:
- `PageEmbeddingSet`, page image, metadata.

Storage per document entry:
- Patch embedding set (for late-interaction scoring).
- Raw page image as base64.
- Metadata: source filename, page number, peripheral keywords.

Output:
- Persistent visual index ready for query-time retrieval.

### Stage 4: Hybrid Retrieval (online)
Input:
- Hardware query string.

Parallel retrieval paths:
- Late-interaction path: MaxSim between query token embeddings and page patch vectors.
- BM25 path: keyword retrieval with explicit boost for `0x[0-9A-Fa-f]+` tokens.

Fusion:
- Reciprocal Rank Fusion (RRF) combines rankings.

Output:
- Top-k page image candidates (typically 3 to 5) with ranking evidence.

### Stage 5: VLM Register and Timing Extractor (online)
Input:
- Retrieved page images and extraction prompt.

Model options:
- LLaVA for open deployment.
- GPT-4V for benchmarking/high-accuracy runs.

Output format (strict JSON-only):
```json
{
  "peripheral": "USART2",
  "register_name": "USART_CR1",
  "base_address": "0x40004400",
  "offset": "0x00",
  "bits": [
    { "name": "UE", "position": 0, "width": 1, "access": "RW" },
    { "name": "RE", "position": 2, "width": 1, "access": "RW" },
    { "name": "TE", "position": 3, "width": 1, "access": "RW" }
  ],
  "timing_constraints": [
    {
      "name": "fPCLK_max",
      "min": null,
      "typ": null,
      "max": 80000000,
      "unit": "Hz",
      "condition": "VDD >= 2.7V"
    }
  ]
}
```

### Stage 6: SVD and Symbolic Validator (online)
Input:
- Extracted register JSON.
- Target MCU CMSIS-SVD XML.
- Optional extracted timing constraints.

Checks in order:
1. Address range check:
   - `(base_address + offset)` must be inside peripheral range from SVD.
2. Bit-field arithmetic check:
   - For each field, `position + width <= register_size`.
   - No overlapping field ranges.
3. Name fuzzy-match check:
   - Register name must match SVD within Levenshtein distance <= 2.
4. Timing consistency check:
  - Normalize all units to canonical units before comparison.
  - Enforce monotonicity when values exist (`min <= typ <= max`).
  - Detect duplicate timing tuples with conflicting values for the same `name` and `condition`.

Output:
- `ValidationResult` with register and timing pass/fail status.
- On fail: machine-readable mismatch report.

### Stage 7: CoVe Re-prompt Loop (fail path)
Trigger:
- Any validator check failure.

Processing:
- Inject mismatch report back to extractor as explicit correction context.
- Retry extraction up to 3 iterations.

Termination:
- Success: pass to synthesis.
- Fail after 3 attempts: emit `UNCERTAIN`, route to human review.

### Stage 8: Code Synthesis Agent (online)
Input:
- Validated register and timing JSON only.

Output artifacts:
- `driver.h`: register addresses/bit masks and declarations.
- `driver.c`: init and access functions.
- `audit_trace.json`: mapping each define or timing constant to validation proof and source page.

### Stage 9: Verified C Driver Output
Verification:
- Compute PASS@K by diffing every generated address in `driver.h` against SVD ground truth.
- Compute timing tuple F1 against labeled timing-table ground truth.
- Compute median time-to-first-driver reduction against manual baseline workflow.

Final deliverables:
- `driver.h`
- `driver.c`
- `audit_trace.json`

## 4. Canonical Data Models

### PageIndexEntry
```json
{
  "doc_id": "stm32l4_rm0351_p123",
  "source_file": "RM0351.pdf",
  "page_number": 123,
  "image_b64": "<base64>",
  "patch_embeddings": [[0.1, -0.2, 0.03]],
  "keywords": ["USART2", "CR1", "0x40004400"]
}
```

### ValidationMismatchReport
```json
{
  "status": "FAIL",
  "checks": {
    "address_range": { "ok": false, "expected": "0x40004400", "actual": "0x40004800" },
    "bit_arithmetic": { "ok": true },
    "name_fuzzy": { "ok": true, "distance": 0 },
    "timing_consistency": { "ok": false, "reason": "min greater than max for tSU" }
  },
  "message": "Base address mismatch for USART2"
}
```

### TimingConstraint
```json
{
  "name": "tSU",
  "min": 50,
  "typ": 80,
  "max": 120,
  "unit": "ns",
  "condition": "I2C Fast Mode"
}
```

## 5. Orchestration Logic

Pseudo-flow:
1. Retrieve top-k pages.
2. Extract JSON with VLM.
3. Validate register facts against SVD and timing facts with deterministic checks.
4. If fail and attempts < 3, run CoVe re-prompt and retry.
5. If pass, synthesize code + audit trace.
6. If still fail after 3 attempts, emit UNCERTAIN.
7. If query requires timing output and timing remains unverified, always emit UNCERTAIN.

## 6. Non-Functional Requirements

- Determinism: validator and synthesis outputs must be reproducible.
- Traceability: every generated symbol must include provenance.
- Safety: fail-closed by default; no silent fallback to unverified outputs.
- Scalability: support datasheets up to 1500 pages with reusable offline indexes.
- Throughput SLO: indexing throughput >= 20 pages/min on reference GPU at 300 dpi.
- Latency SLO: retrieval p95 <= 1.5 s and retrieval+extraction+validation p95 <= 20 s for `k <= 5`.
- Productivity KPI: median time-to-first-driver reduction >= 40% versus manual baseline.
- Observability: stage-level logs, retry counts, and mismatch taxonomy.

## 7. Decision Log

| ID | Decision | Rationale | Status |
|---|---|---|---|
| ADR-001 | Image-first ingestion, no OCR | Preserve table/bitfield structure and avoid OCR noise | Accepted |
| ADR-002 | Hybrid retrieval with RRF | Balance semantic similarity with exact hex matches | Accepted |
| ADR-003 | SVD as validation oracle | Deterministic guardrail against hallucinations | Accepted |
| ADR-004 | Bounded CoVe retries (max 3) | Improve extraction while preventing infinite loops | Accepted |
| ADR-005 | Provenance artifact required | Needed for safety/compliance workflows | Accepted |
| ADR-006 | Typed timing tuple model + deterministic timing checks | Covers timing tables while keeping validation deterministic | Accepted |
| ADR-007 | Explicit scale and latency SLO targets | Keeps system practical for large datasheets | Accepted |

## 8. Open Questions

- Which VLM should be production default for cost vs quality tradeoff?
- What threshold should trigger immediate UNCERTAIN without retries?
- Should retrieval use dynamic k based on query ambiguity?
- Which timing constraints should be emitted as C constants versus only trace records?
- Which MCU families define the first benchmark suite?
