#!/usr/bin/env python3
"""
Fast validation script for KarcinoJen setup.

Validates:
  1. Data files and directory structure
  2. Configuration files
  3. Schema alignment
  4. API keys in environment
"""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class ValidationResult:
    name: str
    passed: bool
    details: str

results: list[ValidationResult] = []

def check(name: str, condition: bool, details: str = "") -> None:
    status = "✓" if condition else "✗"
    print(f"{status} {name}" + (f": {details}" if details else ""))
    results.append(ValidationResult(name, condition, details))

def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ────────────────────────────────────────────────────────────────────────────────
section("1. Python Environment")

# Check Python version
python_version = sys.version_info
check("Python version >= 3.11",
      python_version.major == 3 and python_version.minor >= 11,
      f"Found {python_version.major}.{python_version.minor}")

print("\nNote: Full dependency validation will run during first pipeline execution.")


# ────────────────────────────────────────────────────────────────────────────────
section("2. Data Files and Directory Structure")

dirs_to_check = {
    "data/datasheets": "Datasheets (PDF)",
    "data/svd": "SVD files (MCU specifications)",
    "data/mcu-bench": "MCU-Bench benchmark dataset",
    "configs": "Configuration files",
    "src": "Source code modules",
    "scripts": "Pipeline scripts",
}

for dir_path, description in dirs_to_check.items():
    full_path = ROOT / dir_path
    file_count = len(list(full_path.glob("*"))) if full_path.exists() else 0
    check(f"{dir_path}", full_path.exists(),
          f"{description} ({file_count} items)" if full_path.exists() else description)

# Check for critical files
files_to_check = {
    "configs/model_config.json": "Runtime configuration",
    "schemas/register_extraction.schema.json": "Extraction schema",
    "data/mcu-bench/benchmark.json": "Benchmark dataset",
    "scripts/run_pipeline.py": "Single-query pipeline",
    "scripts/run_tests.py": "Test harness",
    "scripts/run_experiment.py": "Paper experiment runner",
    "requirements.txt": "Project dependencies",
}

for file_path, description in files_to_check.items():
    full_path = ROOT / file_path
    check(f"{file_path}", full_path.exists(), description)

# ────────────────────────────────────────────────────────────────────────────────
section("3. Configuration and Schema Files")

try:
    config_path = ROOT / "configs" / "model_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    
    check("Config version", "version" in config, f"v{config.get('version', 'N/A')}")
    check("Gemini provider configured", "gemini" in config.get("providers", {}))
    check("Groq provider configured", "groq" in config.get("providers", {}))
    check("Qwen2.5-VL provider configured", "qwen2_5_vl" in config.get("providers", {}))
    
    retrieval_cfg = config.get("retrieval", {})
    check("Retrieval backend (ColPali)", retrieval_cfg.get("backend") == "colpali",
          f"Currently: {retrieval_cfg.get('backend')}")
    
except Exception as e:
    check("Configuration file validation", False, str(e)[:60])

try:
    schema_path = ROOT / "schemas" / "register_extraction.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required = schema.get("required", [])
    check("Extraction schema valid", len(required) > 0,
          f"Required fields: {', '.join(required)}")
    
except Exception as e:
    check("Schema validation", False, str(e)[:60])

# ────────────────────────────────────────────────────────────────────────────────
section("4. Benchmark Dataset")

try:
    benchmark_path = ROOT / "data" / "mcu-bench" / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    
    records = benchmark.get("records", [])
    check("Benchmark records", len(records) > 0, f"{len(records)} queries")
    
    if records:
        first = records[0]
        required_fields = ["id", "query", "peripheral", "register", "datasheet_stem", "svd_stem"]
        missing = [f for f in required_fields if f not in first]
        check("Benchmark record structure", len(missing) == 0,
              f"All fields present" if not missing else f"Missing: {missing}")
        
        has_gt = "ground_truth" in first or "ground_truth_json" in first
        check("Ground truth data", has_gt, "Both formats available")
    
except Exception as e:
    check("Benchmark validation", False, str(e)[:60])

# ────────────────────────────────────────────────────────────────────────────────
section("5. API Keys and Environment")

load_env_file = False
env_path = ROOT / ".env"
if env_path.exists():
    load_env_file = True
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value and key not in os.environ:
                    os.environ[key] = value
    except:
        pass

gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

check(".env file", env_path.exists())
check("GEMINI_API_KEY in environment", bool(gemini_key), "Required" if not gemini_key else "✓")
check("GROQ_API_KEY in environment", bool(groq_key), "Required" if not groq_key else "✓")

# ────────────────────────────────────────────────────────────────────────────────
section("6. Python Modules (Quick Check)")

key_modules = [
    "src/extractor/vlm_client.py",
    "src/retrieval/hybrid_retriever.py",
    "src/evaluation/pass_at_k.py",
    "src/validator/svd_validator.py",
]

for mod_path in key_modules:
    full_path = ROOT / mod_path
    check(f"Module: {mod_path}", full_path.exists())

# ────────────────────────────────────────────────────────────────────────────────
section("Summary")

total = len(results)
passed = sum(1 for r in results if r.passed)
failed = total - passed

print(f"\nValidation Results: {passed}/{total} checks passed")

if failed > 0:
    print(f"\n⚠ {failed} check(s) need attention:")
    for r in results:
        if not r.passed:
            print(f"  • {r.name}")
else:
    print("\n✓ All critical checks passed!")

print("\n" + "="*70)
print("NEXT STEPS:")
print("="*70)
print("""
1. Install dependencies with CUDA support:
   pip install torch --index-url https://download.pytorch.org/whl/cu118
   pip install -r requirements.txt

2. Set required API keys in environment:
   export GEMINI_API_KEY="your-key-here"
   export GROQ_API_KEY="your-key-here"

3. Run a quick test:
   python scripts/run_pipeline.py \\
     --datasheet data/datasheets/stm32f401-rm.pdf \\
     --query "Extract GPIOA MODER register bit layout..."

4. Run full test suite:
   python scripts/run_tests.py

5. Run paper experiment (all 3 configurations):
   python scripts/run_experiment.py

6. For Google Colab:
   - Open notebooks/KarcinoJen_Colab.ipynb
   - Set runtime to GPU
   - Run cells in order

8. For GPU-accelerated runs:
   - Ensure CUDA-enabled torch is installed
   - ColPali will auto-use GPU for visual embeddings
""")
print("="*70)

sys.exit(0 if failed == 0 else 1)

