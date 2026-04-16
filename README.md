# KarcinoJen

KarcinoJen is a research prototype for generating traceable MCU driver artifacts from datasheet-derived register data.

## Current Repository State

Implemented now:
- Package A data assets: benchmark manifest, query set, page catalog, and ground-truth JSONL.
- Package B core reliability code: schema harness, deterministic SVD validator, CoVe loop, taxonomy evidence runner.
- Package C synthesis and demo: C code generator and deterministic replay/live demo scripts.
- Integrated runner: one command that stitches A+B+C artifacts with config-driven retrieval and optional live VLM extraction.
- Retrieval runtime modules: page catalog index loader and hybrid lexical+semantic retrieval with reciprocal-rank fusion.
- Stage 5 extraction modules: provider-based VLM client for OpenAI GPT-4o or LLaVA endpoints.

Not implemented yet:
- Embedding/vector retrieval stack (for example ColPali + ChromaDB).
- Full visual prompt formatting beyond current page-context packaging.

## Inputs

Primary project input conceptually:
- MCU datasheet PDF.

Inputs currently used by code:
- A query and benchmark assets in data/mcu-bench/.
- SVD files in data/svd/.
- Fixture extraction payloads for deterministic runs.
- Versioned runtime model/retrieval config in configs/model_config.json.

## Model Usage Right Now

- CoVe: yes, implemented in src/orchestration/cove_loop.py as deterministic correction logic with max 3 attempts.
- VLM: called in vlm-live mode through src/extractor/vlm_client.py (OpenAI or LLaVA, based on config).
- LLM: no separate LLM call path; extraction uses the configured VLM endpoint.

## How To Run

From repository root:

1) Run integrated A+B+C pipeline (ground-truth backed deterministic run)

python scripts/run_pipeline.py --mode ground-truth --query-id mcu_bench_005

Artifacts are written to runs/pipeline/<timestamp>/.

2) Run integrated pipeline with live Stage 5 VLM extraction

Set provider credentials first (depends on configs/model_config.json):

PowerShell (OpenAI):
$env:OPENAI_API_KEY="<your_key>"

PowerShell (LLaVA endpoint mode):
$env:LLAVA_ENDPOINT="http://localhost:11434/api/generate"

Then run:

python scripts/run_pipeline.py --mode vlm-live --query-id mcu_bench_005 --top-k 3

3) Run Package B reliability artifacts only

python scripts/run_package_b.py

Artifacts are written to artifacts/package_b/<timestamp>/.

4) Run synthesis demo (Package C)

python scripts/run_demo.py --replay

or live synthesis with fixture:

python scripts/run_demo.py --input tests/fixtures/validated_stm32l4.json

## Tests

python -m unittest discover -s tests/unit -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_*.py"

## Key Paths

- docs/architecture.md
- configs/model_config.json
- data/mcu-bench/queries.jsonl
- data/mcu-bench/ground_truth.jsonl
- src/index/page_index.py
- src/retrieval/hybrid_retriever.py
- src/extractor/model_config.py
- src/extractor/vlm_client.py
- src/extractor/vlm_extractor.py
- src/validator/svd_validator.py
- src/orchestration/cove_loop.py
- src/synthesis/synthesize.py
- scripts/run_pipeline.py
- scripts/run_package_b.py
- scripts/run_demo.py
