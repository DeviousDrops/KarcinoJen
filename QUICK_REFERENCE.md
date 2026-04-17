# KarcinoJen: Quick Reference Card

## 🚀 Quick Start (5 Minutes)

### Option A: Google Colab (No Installation)
```
1. Open: notebooks/KarcinoJen_Colab.ipynb
2. Click: "Open in Colab" badge or paste URL in colab.research.google.com
3. Set: Runtime → Change runtime type → GPU
4. Run: Cells 1-7 in order (auto-installs everything)
```

### Option B: Local GPU (20 Minutes)
```bash
# 1. Setup environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install CUDA torch
pip install torch --index-url https://download.pytorch.org/whl/cu118

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set API keys (create .env file or export)
export GEMINI_API_KEY="sk-..."
export GROQ_API_KEY="gsk-..."

# 5. Verify setup
python scripts/validate_setup.py
```

---

## 📋 Common Commands

### Run Single Query
```bash
python scripts/run_pipeline.py \
  --datasheet data/datasheets/stm32f401-rm.pdf \
  --query "Extract GPIOA MODER register..."
```

### Run All 5 Test Cases
```bash
python scripts/run_tests.py
```

### Run One Test Case
```bash
python scripts/run_tests.py --case 1
```

### Compare Retrieval Backends
```bash
python scripts/run_tests.py --backend colpali  # GPU visual embeddings
python scripts/run_tests.py --backend lexical  # CPU BM25 fallback
```

### Run Full Paper Experiment (17 queries × 3 configurations)
```bash
python scripts/run_experiment.py
# Output: runs/experiments/<timestamp>/experiment_report.json
```

### Validate Setup (30 checks)
```bash
python scripts/validate_setup.py
```

---

## 🔌 API Keys

### Get Keys

| Provider | URL | Type |
|----------|-----|------|
| **Gemini** | https://aistudio.google.com/apikey | API Key |
| **Groq** | https://console.groq.com | API Key |
| **OpenAI** (optional) | https://platform.openai.com/api-keys | API Key |

### Set Keys

**Option 1: Environment Variables**
```bash
export GEMINI_API_KEY="sk-..."
export GROQ_API_KEY="gsk-..."
```

**Option 2: .env File**
```
GEMINI_API_KEY=sk-...
GROQ_API_KEY=gsk-...
```

**Option 3: Colab (Interactive)**
```python
# In Colab notebook - prompted automatically
```

---

## 📊 What You'll Get

```
Output files in: generated/drivers/<timestamp>/

driver.h
├─ Register address defines (#define GPIOA_ADDR 0x40020000)
├─ Bit field macros
└─ Memory layout documentation

driver.c
├─ Register read/write functions
├─ Validation logic
└─ Comments with extraction provenance

audit_trace.json
├─ Retrieval results (top-5 pages + scores)
├─ Extraction attempts (retry history)
├─ SVD validation results
├─ Synthesis output
└─ PASS@K accuracy metrics
```

---

## 🎯 Expected Performance

| Hardware | ColPali Retrieval | Full Pipeline | Notes |
|----------|------------------|---------------|-------|
| **GPU (A100)** | 2-5s | 15-30s | Recommended for paper |
| **GPU (V100)** | 5-10s | 20-40s | Good for experiments |
| **GPU (T4/Colab)** | 8-15s | 25-50s | Free tier in Colab |
| **CPU** | 30-45s | 60-90s | Fallback (slow) |

**PASS@K Accuracy:**
- Baseline 1 (VLM only): ~40-50%
- Baseline 2 (VLM + validation): ~70-80%
- Full KarcinoJen (+ CoVe retries): ~85-95%

---

## ⚙️ Configuration

Edit `configs/model_config.json` to customize:

```json
{
  "selected_provider": "gemini",          // VLM provider
  "retrieval": {
    "backend": "colpali",                 // or "lexical"
    "top_k": 5                            // number of pages to retrieve
  },
  "extraction": {
    "temperature": 0,                     // 0=deterministic, >0=creative
    "max_attempts": 3                     // CoVe retry limit
  }
}
```

---

## 🐛 Common Issues & Fixes

| Problem | Fix |
|---------|-----|
| **"CUDA not available"** | `pip install torch --index-url https://download.pytorch.org/whl/cu118` |
| **"ModuleNotFoundError"** | `pip install -r requirements.txt` |
| **"GEMINI_API_KEY not found"** | Create `.env` file or `export GEMINI_API_KEY="sk-..."` |
| **"Out of memory (OOM)"** | Use `--backend lexical` or reduce `top_k` in config |
| **"Slow on my machine"** | Check GPU: `nvidia-smi` or switch to Colab |
| **"Ollama not responding"** | Run `ollama serve` in separate terminal |

---

## 📚 Full Documentation

- **Setup Guide**: [docs/CUDA_COLAB_SETUP.md](docs/CUDA_COLAB_SETUP.md)
- **Architecture**: [docs/architecture.md](docs/architecture.md)
- **Implementation Plan**: [docs/implementation-plan.md](docs/implementation-plan.md)
- **Completion Summary**: [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md)

---

## 🔗 Key Files

```
KarcinoJen/
├── scripts/
│   ├── run_pipeline.py           # Single query execution
│   ├── run_tests.py              # 5 test cases
│   ├── run_experiment.py         # Full 17-query benchmark (3 configs)
│   └── validate_setup.py         # 30-point setup check
├── notebooks/
│   └── KarcinoJen_Colab.ipynb   # Interactive Colab notebook
├── configs/
│   └── model_config.json         # Runtime configuration
├── data/
│   ├── datasheets/               # PDF datasheets
│   ├── svd/                      # MCU specifications (XML)
│   └── mcu-bench/                # 17 benchmark queries
├── src/
│   ├── retrieval/                # ColPali + lexical
│   ├── extractor/                # Gemini, LLaVA, Qwen2.5-VL
│   ├── validator/                # SVD validation
│   ├── synthesis/                # Groq synthesis
│   └── evaluation/               # PASS@K metrics
└── docs/
    ├── CUDA_COLAB_SETUP.md       # Detailed setup guide
    ├── architecture.md            # System design
    └── implementation-plan.md     # Experiment details
```

---

## 💡 Tips

**For Best Results:**
1. Use Colab for quick iteration (free GPU, no setup)
2. Use local GPU for paper runs (more control)
3. Set `top_k: 5` in config (good balance)
4. Use Gemini primary (best accuracy)
5. Enable CoVe for evaluation (better PASS@K)

**For Low-Resource Environments:**
1. Use `--backend lexical` (no GPU needed)
2. Set `temperature: 0` (smaller outputs)
3. Use Groq for synthesis (faster than local)
4. Reduce `top_k` to 3

**For Development:**
1. Run individual test cases: `--case 1`
2. Check logs: `--verbose`
3. Validate config: `python scripts/validate_setup.py`
4. Use Colab for experiments (free GPU hours)

---

## ✅ You're Ready!

```bash
# Verify everything is working
python scripts/validate_setup.py

# Run your first extraction
python scripts/run_pipeline.py \
  --datasheet data/datasheets/stm32f401-rm.pdf \
  --query "Extract GPIOA MODER register bit layout..."

# Expected output: driver.h, driver.c, audit_trace.json with PASS@K score
```

**Need help?** See [docs/CUDA_COLAB_SETUP.md](docs/CUDA_COLAB_SETUP.md) or check the TROUBLESHOOTING section there.
