# KarcinoJen: CUDA Setup & Google Colab Guide

This document provides step-by-step instructions for setting up KarcinoJen with CUDA acceleration and running on Google Colab.

## Table of Contents

1. [Local CUDA Setup (Windows/Linux/Mac)](#local-cuda-setup)
2. [Google Colab Setup](#google-colab-setup)
3. [Verification and Testing](#verification-and-testing)
4. [Troubleshooting](#troubleshooting)

---

## Local CUDA Setup

### Prerequisites

- **Python 3.11+** (check with `python --version`)
- **NVIDIA GPU** (RTX 3080/4090 recommended for ColPali; V100/A100 for Colab)
- **CUDA 11.8+** (for GPU-accelerated PyTorch)
- **Git** (for cloning the repository)

### Step 1: Clone Repository

```bash
git clone <repository-url> KarcinoJen
cd KarcinoJen
```

### Step 2: Create Python Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install CUDA-Enabled PyTorch

The `requirements.txt` includes a comment about CUDA torch. Install with CUDA 11.8 support:

```bash
# Install torch with CUDA 11.8 (compatible with most modern GPUs)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For CUDA 12.1 (newer GPUs like RTX 40-series):
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Step 4: Install Project Dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Configure API Keys

Create a `.env` file in the project root with your API keys:

```bash
# .env (do NOT commit this file)
GEMINI_API_KEY=sk-xxxxxxxxxxxxx  # Get from https://aistudio.google.com/apikey
GROQ_API_KEY=gsk-xxxxxxxxxxxxxxx  # Get from https://console.groq.com
# Optional:
OPENAI_API_KEY=sk-xxxxx  # For OpenAI fallback
OLLAMA_ENDPOINT=http://localhost:11434  # For local LLaVA/Qwen2.5-VL
```

Or set via environment variables:

```bash
# Windows PowerShell
$env:GEMINI_API_KEY = "sk-xxxxxxxxxxxxx"
$env:GROQ_API_KEY = "gsk-xxxxxxxxxxxxxxx"

# Linux/Mac bash
export GEMINI_API_KEY="sk-xxxxxxxxxxxxx"
export GROQ_API_KEY="gsk-xxxxxxxxxxxxxxx"
```

### Step 6: Verify CUDA Setup

```bash
# Check GPU availability
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
python -c "import torch; print(f'CUDA Version: {torch.version.cuda}')"

# Run project validation
python scripts/validate_setup.py
```

### Step 7: Run a Quick Test

```bash
# Single-query pipeline (STM32F401 USART2 CR1 extraction)
python scripts/run_pipeline.py \
  --datasheet data/datasheets/stm32f401-rm.pdf \
  --query "Extract USART2 CR1 control bits including UE, M, PCE, TE, and RE with bit positions."

# This should:
# 1. Retrieve top-5 pages using ColPali visual embeddings (GPU-accelerated)
# 2. Extract register info using Gemini 2.5 Flash VLM
# 3. Validate against SVD specification
# 4. Generate driver.h/driver.c
# 5. Display PASS@K accuracy score
```

### Step 8: Run Full Test Suite

```bash
# Run all 5 test cases (tests/run_tests.py)
python scripts/run_tests.py

# Or run with specific backend:
python scripts/run_tests.py --backend colpali
python scripts/run_tests.py --backend lexical  # CPU fallback

# Or run single test case:
python scripts/run_tests.py --case 1
```

### Step 9: Run Paper Experiment (All 3 Configurations)

```bash
# Runs baselines and full KarcinoJen across all 17 MCU-Bench queries
python scripts/run_experiment.py

# Output: runs/experiments/<timestamp>/experiment_report.json
# Contains: PASS@K, CoVe recovery rates, error analysis
```

---

## Google Colab Setup

### Overview

The `notebooks/KarcinoJen_Colab.ipynb` notebook is pre-configured for Colab with:
- GPU runtime detection and setup
- CUDA-enabled torch installation
- API key prompts
- Example pipeline execution

### Step 1: Prepare Repository on GitHub

Colab requires the repository to be on GitHub or Google Drive. Recommended approach:

```bash
# Option A: Push to GitHub
git remote add origin https://github.com/yourusername/KarcinoJen.git
git branch -M main
git push -u origin main
```

### Step 2: Open Notebook in Colab

1. Go to https://colab.research.google.com
2. Click **File** → **Open notebook** → **GitHub**
3. Paste your repository URL (e.g., `https://github.com/yourusername/KarcinoJen`)
4. Select `notebooks/KarcinoJen_Colab.ipynb`

Or use direct link:
```
https://colab.research.google.com/github/yourusername/KarcinoJen/blob/main/notebooks/KarcinoJen_Colab.ipynb
```

### Step 3: Set GPU Runtime

1. In Colab, click **Runtime** → **Change runtime type**
2. Select **Hardware accelerator: GPU** (A100/V100/T4)
3. Click **Save**

### Step 4: Run Notebook Cells in Order

**Cell 1:** Repository Setup
```python
# Clones repo or uses existing copy
# Output: "Working directory: /content/KarcinoJen"
```

**Cell 2:** Install Dependencies with CUDA
```python
# Installs PyTorch with CUDA 11.8 support
# Installs project requirements
# Takes 2-3 minutes
```

**Cell 3:** Verify CUDA/GPU
```python
# Checks NVIDIA GPU detection
# Verifies PyTorch CUDA support
# Shows GPU memory and specs
```

**Cell 4:** Data Verification
```python
# Ensures datasheets and SVDs are present
# Notes: ColPali embeddings auto-generate on first run (2-5 min)
```

**Cell 5:** Set API Keys
```python
# Prompts for GEMINI_API_KEY
# Prompts for GROQ_API_KEY
# Keys stored in session environment (secure)
```

**Cell 6:** Configure Runtime Profile
```python
# Sets default: ColPali retrieval + Gemini extraction + Groq synthesis
# Customizable via set_runtime_profile()
```

**Cell 7:** Run Single Query Pipeline
```python
# Example: STM32 USART2 CR1 register extraction
# Output: driver.h, driver.c, PASS@K score
# Takes 30-60 seconds (includes ColPali embedding generation on first run)
```

**Cell 8:** Run Ablation (Lexical-Only Fallback)
```python
# Optional: Tests retrieval fallback without ColPali GPU acceleration
# Demonstrates resource-constrained scenario
```

### Step 5: Accessing Generated Files

Generated outputs are stored in:
```
/content/KarcinoJen/generated/drivers/<timestamp>/
  - driver.h          (generated register defines)
  - driver.c          (generated driver implementation)
  - audit_trace.json  (provenance and validation steps)
```

To download:

```python
# In Colab cell:
from google.colab import files
import zipfile
from pathlib import Path

# Create archive of latest generated drivers
latest_dir = sorted(Path("/content/KarcinoJen/generated/drivers").iterdir())[-1]
with zipfile.ZipFile("/tmp/outputs.zip", "w") as z:
    for f in latest_dir.rglob("*"):
        if f.is_file():
            z.write(f, arcname=f.relative_to(latest_dir.parent))

files.download("/tmp/outputs.zip")
```

### GPU Memory Management (Colab)

If you encounter out-of-memory (OOM) errors:

```python
# In Colab cell, before pipeline execution:
import torch
torch.cuda.empty_cache()

# Or reduce batch size:
# Edit configs/model_config.json and lower extraction.temperature or use lexical fallback
```

---

## Verification and Testing

### Validation Checklist

After setup, verify everything:

```bash
# Run validation script
python scripts/validate_setup.py
```

Expected output: **30/30 checks passed**

This validates:
- ✓ Python 3.11+ environment
- ✓ Data files (datasheets, SVDs, benchmark)
- ✓ Configuration files (model_config.json, schemas)
- ✓ API key environment variables
- ✓ Module imports and compilation
- ✓ Benchmark schema alignment

### Quick Test Scenarios

**Test 1: ColPali Retrieval (GPU)**
```bash
python scripts/run_tests.py --backend colpali --case 1
```

Expected: Retrieves top-5 pages in 5-10 seconds on GPU (30+ seconds on CPU)

**Test 2: Lexical Fallback (CPU)**
```bash
python scripts/run_tests.py --backend lexical --case 1
```

Expected: Retrieves via BM25 token matching in <1 second

**Test 3: VLM Fallback Chain**
```bash
# Gemini → LLaVA → Qwen2.5-VL
# If GEMINI_API_KEY fails, automatically tries next provider
python scripts/run_tests.py --case 2
```

**Test 4: Full Paper Experiment**
```bash
python scripts/run_experiment.py
```

Expected: Runs 17 queries × 3 configurations, outputs:
- PASS@K scores (address accuracy)
- CoVe recovery rates
- Error taxonomy breakdown

---

## Troubleshooting

### Common Issues

#### Issue: "ModuleNotFoundError: No module named 'torch'"

**Solution:**
```bash
# Reinstall torch with CUDA
pip uninstall torch -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

#### Issue: "CUDA out of memory (OOM)"

**Solution (Local):**
```bash
# Use CPU fallback
python scripts/run_tests.py --backend lexical

# Or reduce batch size in configs/model_config.json
```

**Solution (Colab):**
```python
# In notebook:
import torch
torch.cuda.empty_cache()
```

#### Issue: "GEMINI_API_KEY not found"

**Solution:**
1. Get key from https://aistudio.google.com/apikey
2. Create `.env` file with `GEMINI_API_KEY=sk-...`
3. Or set environment variable: `export GEMINI_API_KEY=sk-...`
4. Verify: `python -c "import os; print(os.getenv('GEMINI_API_KEY'))"`

#### Issue: "No such file or directory: 'data/datasheets/stm32f401-rm.pdf'"

**Solution:**
- Datasheets must be present in `data/datasheets/`
- On Colab, they auto-download from repo on first cell
- Verify with: `python scripts/validate_setup.py`

#### Issue: "Ollama endpoint not responding" (for Qwen2.5-VL)

**Solution:**
1. Start Ollama locally: `ollama serve`
2. Pull model: `ollama pull qwen2.5-vl:7b`
3. Set endpoint: `export OLLAMA_ENDPOINT=http://localhost:11434`
4. Or use Gemini/LLaVA fallback (no local setup needed)

#### Issue: "Slow ColPali retrieval on CPU"

**Solution:**
1. Ensure CUDA torch is installed: `python -c "import torch; print(torch.cuda.is_available())"`
2. If False, reinstall with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118`
3. Or use lexical fallback: `python scripts/run_tests.py --backend lexical`

### Performance Benchmarks

| Scenario | GPU (V100) | GPU (A100) | CPU |
|----------|-----------|-----------|-----|
| ColPali Retrieval (1 query) | 5-10s | 2-5s | 30-45s |
| Gemini Extraction (5 pages) | 10-20s | 10-20s | 10-20s |
| SVD Validation + CoVe | <1s | <1s | <1s |
| Full Pipeline (1 query) | 20-40s | 15-30s | 60-90s |
| MCU-Bench Experiment (17 queries × 3 configs) | 5-8 min | 3-5 min | 20+ min |

---

## Advanced Configuration

### Custom Provider Settings

Edit `configs/model_config.json`:

```json
{
  "selected_provider": "gemini",  // or "groq", "openai", "ollama"
  "providers": {
    "gemini": {
      "model": "gemini-2.5-flash",
      "timeout_seconds": 90
    },
    "groq": {
      "model": "llama-3.3-70b-versatile",
      "timeout_seconds": 60
    },
    "qwen2_5_vl": {
      "endpoint_env": "OLLAMA_ENDPOINT",
      "timeout_seconds": 240
    }
  }
}
```

### Retrieval Backend Settings

```json
{
  "retrieval": {
    "backend": "colpali",  // or "lexical"
    "top_k": 5,
    "colpali_model": "vidore/colpali-v1.3-merged",
    "colpali_index_path": "data/colpali_index",
    "lexical_weight": 0.35,
    "semantic_weight": 0.65,
    "hex_token_boost": 2.0
  }
}
```

### Extraction Settings

```json
{
  "extraction": {
    "temperature": 0,      // deterministic (0) vs creative (>0)
    "max_attempts": 3,     // CoVe retry limit
    "response_format": "json_object"
  }
}
```

---

## Next Steps

1. **Read the README.md** for architecture overview
2. **Check docs/architecture.md** for system design
3. **Review docs/implementation-plan.md** for experiment setup
4. **Run notebooks/KarcinoJen_Colab.ipynb** for interactive demo

For questions or issues, refer to troubleshooting section above.
