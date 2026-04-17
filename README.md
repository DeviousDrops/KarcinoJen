# KarcinoJen

KarcinoJen turns a datasheet and a natural-language register query into generated driver code.

## Quick Start

### GPU-Accelerated Local Setup (Recommended)

For maximum performance with ColPali visual embeddings on your GPU:

```bash
# 1. Clone and setup
git clone <repo-url> KarcinoJen && cd KarcinoJen
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 2. Install PyTorch with CUDA support
pip install torch --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt

# 3. Set API keys
export GEMINI_API_KEY="sk-..."
export GROQ_API_KEY="gsk-..."

# 4. Verify setup
python scripts/validate_setup.py

# 5. Run your first extraction
python scripts/run_pipeline.py --datasheet data/datasheets/stm32f401-rm.pdf --query "Extract GPIOA MODER register..."
```

### Google Colab (Free GPU)

Open in Colab (**recommended for no local setup**):
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_USERNAME/KarcinoJen/blob/main/notebooks/KarcinoJen_Colab.ipynb)

Or follow the notebook walkthrough in [docs/CUDA_COLAB_SETUP.md](docs/CUDA_COLAB_SETUP.md#google-colab-setup).

---

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

- **CUDA Setup**: See [docs/CUDA_COLAB_SETUP.md](docs/CUDA_COLAB_SETUP.md) for detailed GPU acceleration setup and troubleshooting.
- **Google Colab**: Pre-configured notebook in `notebooks/KarcinoJen_Colab.ipynb` with automatic GPU and dependency setup.
- The old benchmark-style package runners and replay modes are no longer the main path.
- The pipeline keeps validation as a guardrail, but it is not exposed as a separate mode.
- You still need a configured Python 3.11 environment with the project dependencies installed.

## Retrieval Utilities

You can compare ColPali and lexical retrieval quality and latency:

```powershell
python scripts/run_tests.py --backend colpali
```

For a lexical fallback run:

```powershell
python scripts/run_tests.py --backend lexical
```

ColPali remains the canonical retrieval path. Lexical is the reliability fallback and ablation.

## Recommendation For Project And Paper

For the paper, the best free and efficient setup is:

1. Retrieval: ColPali (canonical), with lexical as baseline and fallback.
2. VLM extraction order: Gemini Flash -> LLaVA -> Qwen-VL.
3. Synthesis order: Groq first, then local models via Ollama.

Why this combination fits the use case:
- ColPali preserves visual semantics for table-heavy datasheets.
- Gemini Flash gives a strong multimodal primary extractor.
- Groq gives fast structured text generation without running your own large text model.
- Lexical retrieval stays useful for ablations and low-latency fallback.

If you want one sentence to describe the architecture: ColPali visual retrieval for evidence grounding, Gemini-first VLM extraction with local VLM fallbacks, and Groq-first synthesis with local fallback.

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
