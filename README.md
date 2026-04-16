# KarcinoJen

KarcinoJen turns a datasheet and a natural-language register query into generated driver code.

## What It Does

The supported flow is a single path:
- input a datasheet PDF
- ask for the register or peripheral you want
- retrieve the relevant page context
- run VLM-based extraction with validation feedback
- generate `driver.h` and `driver.c`

## What It Keeps

Only the files that matter for the final driver output are kept by default:
- `driver.h`
- `driver.c`

Everything else is internal implementation detail or temporary scratch space.

## Current Runtime Pieces

- Page scanning and ranking happen directly in [scripts/run_pipeline.py](scripts/run_pipeline.py).
- Extraction: [src/extractor/vlm_client.py](src/extractor/vlm_client.py) and [src/extractor/vlm_extractor.py](src/extractor/vlm_extractor.py)
- Validation guardrails: [src/extractor/schema_harness.py](src/extractor/schema_harness.py) and [src/validator/svd_validator.py](src/validator/svd_validator.py)
- Synthesis: [src/synthesis/synthesize.py](src/synthesis/synthesize.py)

## Configuration

Model and retry settings live in [configs/model_config.json](configs/model_config.json).

OpenAI mode uses `OPENAI_API_KEY`.
LLaVA mode uses `OLLAMA_ENDPOINT`.
The repository includes [.env.example](.env.example) as a template for local secrets and endpoints.

For this branch, the local vision provider is Ollama `llava` and it uses `OLLAMA_ENDPOINT`.

## How To Run

From the repository root, run:

```powershell
python scripts/run_pipeline.py --datasheet data/datasheets/stm32f401-rm.pdf --query "Extract GPIOA MODER register bit layout for pins 0 to 3 and explain mode encoding width per pin."
```

The generated driver files are written under `generated/drivers/<timestamp>/` by default.

If you want to change the output location:

```powershell
python scripts/run_pipeline.py --datasheet data/datasheets/stm32f401-rm.pdf --query "Extract USART2 CR1 control bits including UE, M, PCE, TE, and RE with bit positions." --outdir generated/my-driver
```

## Notes

- The old benchmark-style package runners and replay modes are no longer the main path.
- The pipeline keeps validation as a guardrail, but it is not exposed as a separate mode.
- You still need a configured Python 3.11 environment with the project dependencies installed.

## Retrieval Utilities

You can prebuild Chroma collections for all local datasheets:

```powershell
python scripts/prebuild_chroma_index.py
```

You can compare lexical vs Chroma retrieval quality and latency:

```powershell
python scripts/compare_retrieval_backends.py
```

Optional inputs for comparison:

```powershell
python scripts/compare_retrieval_backends.py --datasheet data/datasheets/stm32f401-ds.pdf --queries data/mcu-bench/queries.jsonl
```

If the `--queries` file is missing, the comparison script runs a built-in fallback query set.

## Recommendation For Project And Paper

For the paper, the best free and efficient setup is:

1. Retrieval: Chroma, with lexical as baseline and fallback.
2. Local vision model: Ollama `llava:7b`.
3. API-key text model: Groq `llama-3.1-8b-instant`.

Why this combination fits the use case:
- Chroma gives you the semantic retrieval story for the paper.
- Ollama Llava keeps the multimodal path fully local and free.
- Groq gives fast structured text generation without running your own large text model.
- Lexical retrieval stays useful for ablations and low-latency fallback.

If you want one sentence to describe the architecture: local vision for evidence reading, Groq for text synthesis and validation, Chroma for retrieval.

## Provider Setup (Ollama And Groq)

You can now choose providers in [configs/model_config.json](configs/model_config.json) with `selected_provider` set to `ollama`, `groq`, `openai`, or `llava`.

### Ollama Local LLM Setup

Install Ollama and pull the vision model:

```powershell
ollama pull llava
```

Optional stronger local text model if you want a fully local non-vision fallback:

```powershell
ollama pull qwen2.5:7b-instruct
```

Set endpoint for the vision path if you want to be explicit:

```powershell
$env:OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
```

Switch config provider:

```json
"selected_provider": "ollama"
```

### Groq API Setup

Recommended Groq model for this project:
- `llama-3.1-8b-instant`

If you want stronger reasoning and Groq availability in your account allows it, try a larger Groq model for comparison, but keep `llama-3.1-8b-instant` as the default paper-friendly free choice.

Set API key in PowerShell:

```powershell
$env:GROQ_API_KEY = "your_groq_api_key"
```

Switch config provider:

```json
"selected_provider": "groq"
```
