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
LLaVA mode uses `LLAVA_ENDPOINT`.

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
