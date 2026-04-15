
---

## Async Contract Status

| Dependency | From | Status |
|---|---|---|
| Validated JSON (B4 output) | Member 2 | 🟡 Waiting — using fixture |
| synthesis output for PASS@K (C1 → A5) | Member 1 needs | ✅ Ready to hand off |
| Demo assets for paper write-up | Member 2 B5 | ✅ Not blocking C |
Save this as docs/PACKAGE_C_README.md and add it to your commit:

text
git add docs/PACKAGE_C_README.md
git commit -m "C3: add Package C readme for teammate handoff"
Prepared using Claude Sonnet 4.6
just make me the readme.md pls
Here's your README.md — copy this exactly:

text
# Package C — Synthesis + Demo

**Owner:** Member 3
**Status:** ✅ Complete (All 3 modules done)
**Branch:** `feat/m3-package-c-synthesis`

---

## What This Package Does

Takes validated JSON from Package B (Member 2) and:
1. Synthesizes `driver.h` and `driver.c` with full register maps
2. Attaches a provenance audit trace to every generated symbol
3. Packages a one-command demo anyone can run

---

## Run the Demo

```cmd
python scripts/run_demo.py --replay
```

That's it. No API calls, no setup, fully deterministic.

For live mode with a real validated JSON:
```cmd
python scripts/run_demo.py --input tests/fixtures/validated_stm32l4.json
```

---

## Current Input Fixture

`tests/fixtures/validated_stm32l4.json` — 3 registers, all PASS.

| Peripheral | Register     | Validation | CoVe Attempts |
|------------|--------------|------------|---------------|
| USART2     | USART_CR1    | PASS       | 1             |
| USART2     | USART_BRR    | PASS       | 1             |
| GPIOA      | GPIOA_MODER  | PASS       | 2             |

When Member 2 hands off real validated JSON, swap it into `--input`. Nothing else changes.

---

## Module C1 — Synthesis Engine ✅

**Script:** `src/synthesis/synthesize.py`

**What it emits:**
- `driver.h` — register address macros + bitmasks for every bit field
- `driver.c` — `_init()`, `_read()`, `_write()` stubs per register
- `audit_trace.json` — provenance record for all 31 symbols

**Run it:**
```cmd
python src/synthesis/synthesize.py \
  --input tests/fixtures/validated_stm32l4.json \
  --outdir runs/c1_smoke/
```

**Tests — 26 passing:**
```cmd
python -m pytest tests/unit/test_synthesize.py -v
```

---

## Module C2 — Demo Script + Replay Bundle ✅

**Script:** `scripts/run_demo.py`

**Replay bundle** (`demo_replay/`):
demo_replay/
├── input_validated.json ← fixture input
├── expected_driver.h ← pre-generated header
├── expected_driver.c ← pre-generated source
└── expected_audit_trace.json ← full provenance trace (31 symbols)

text

---

## Module C3 — Smoke Check + Presenter Notes ✅

- Smoke run artifacts: `runs/smoke_test/`
- Full presenter talking script: `docs/demo_notes.md`

---

## Demo Talking Track

| Step | What to say / show |
|------|--------------------|
| 1 | "Extracting register maps from 1000-page datasheets is error-prone. KarcinoJen automates it." |
| 2 | Show `input_validated.json` — 3 registers, PASS, GPIOA had CoVe retry |
| 3 | Run `python scripts/run_demo.py --replay` |
| 4 | Show `driver.h` — point to `USART2_USART_CR1_ADDR = 0x40004400UL` and bitmasks |
| 5 | Show `audit_trace.json` — every symbol has source page + provenance note |
| 6 | Show `driver.c` — volatile pointer read/write stubs |

---

## Handoff to Member 1 (PASS@K)

Hand off: `demo_replay/expected_audit_trace.json`
- 31 symbols, all `validation_status: PASS`
- GPIOA `validation_attempts: 2` → one CoVe correction case for the error taxonomy table

---

## File Map
src/synthesis/synthesize.py ← synthesis engine
tests/fixtures/validated_stm32l4.json ← mock input fixture
tests/unit/test_synthesize.py ← 26 unit tests
scripts/run_demo.py ← demo runner
demo_replay/ ← replay bundle
runs/c1_smoke/ ← C1 smoke evidence
runs/smoke_test/ ← C3 smoke evidence
docs/demo_notes.md ← presenter notes