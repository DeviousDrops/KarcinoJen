# KarcinoJen

KarcinoJen is a research prototype for generating traceable MCU driver artifacts from datasheet-derived register data.

## Current Repository State

Implemented now:
- Package A data assets: benchmark manifest, query set, page catalog, and ground-truth JSONL.
- Package B core reliability code: schema harness, deterministic SVD validator, CoVe loop, taxonomy evidence runner.
- Package C synthesis and demo: C code generator and deterministic replay/live demo scripts.
- Integrated runner: one command that stitches A+B+C artifacts in the current codebase state.

Not implemented yet:
- Real ingestion/index/retrieval stack (PDF rendering, ColPali embeddings, ChromaDB, RRF).
- Real VLM extraction calls (no GPT-4o/LLaVA API invocation in repository code).

## Inputs

Primary project input conceptually:
- MCU datasheet PDF.

Inputs currently used by code:
- A query and benchmark assets in data/mcu-bench/.
- SVD files in data/svd/.
- Fixture extraction payloads for deterministic runs.

## Model Usage Right Now

- CoVe: yes, implemented in src/orchestration/cove_loop.py as deterministic correction logic with max 3 attempts.
- VLM: not called in current codebase (extraction is simulated from fixtures/ground truth).
- LLM: not called in current codebase.

## How To Run

From repository root:

1) Run integrated A+B+C pipeline (ground-truth backed deterministic run)

python scripts/run_pipeline.py --mode ground-truth --query-id mcu_bench_005

Artifacts are written to runs/pipeline/<timestamp>/.

2) Run Package B reliability artifacts only

python scripts/run_package_b.py

Artifacts are written to artifacts/package_b/<timestamp>/.

3) Run synthesis demo (Package C)

python scripts/run_demo.py --replay

or live synthesis with fixture:

python scripts/run_demo.py --input tests/fixtures/validated_stm32l4.json

## Tests

python -m unittest discover -s tests/unit -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_*.py"

## Key Paths

- docs/architecture.md
- data/mcu-bench/queries.jsonl
- data/mcu-bench/ground_truth.jsonl
- src/validator/svd_validator.py
- src/orchestration/cove_loop.py
- src/synthesis/synthesize.py
- scripts/run_pipeline.py
- scripts/run_package_b.py
- scripts/run_demo.py
