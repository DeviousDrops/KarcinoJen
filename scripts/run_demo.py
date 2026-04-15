#!/usr/bin/env python3
"""
scripts/run_demo.py  —  KarcinoJen Package C, Module C2
One-command demo runner. Two modes:

  LIVE mode   — runs synthesize.py on a given validated JSON input
  REPLAY mode — shows pre-saved artifacts from demo_replay/ without any API calls

Usage:
  python scripts/run_demo.py --input tests/fixtures/validated_stm32l4.json
  python scripts/run_demo.py --replay
  python scripts/run_demo.py --input tests/fixtures/validated_stm32l4.json --out runs/my_run/
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
SYNTHESIZE    = PROJECT_ROOT / "src" / "synthesis" / "synthesize.py"
DEMO_REPLAY   = PROJECT_ROOT / "demo_replay"
FIXTURE       = PROJECT_ROOT / "tests" / "fixtures" / "validated_stm32l4.json"


def _banner(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def _print_file_preview(path: Path, max_lines: int = 30):
    print(f"\n>>> {path.name}  ({path.stat().st_size} bytes)")
    print("-" * 50)
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[:max_lines]:
        print(line)
    if len(lines) > max_lines:
        print(f"  ... [{len(lines) - max_lines} more lines] ...")
    print("-" * 50)


def run_live(input_path: Path, outdir: Path):
    _banner("KarcinoJen Demo — LIVE mode")
    print(f"  Input  : {input_path}")
    print(f"  Output : {outdir}")

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    print(f"\n[demo] Input contains {len(data)} validated register(s):")
    for reg in data:
        print(f"       • {reg['peripheral']}/{reg['register_name']}  "
              f"status={reg.get('validation_status')}  "
              f"attempts={reg.get('validation_attempts')}")

    print(f"\n[demo] Running synthesize.py ...")
    result = subprocess.run(
        [sys.executable, str(SYNTHESIZE),
         "--input",  str(input_path),
         "--outdir", str(outdir)],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("[demo] ERROR: synthesis failed.", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    _banner("Generated Artifacts")
    for fname in ["driver.h", "driver.c", "audit_trace.json"]:
        fpath = outdir / fname
        if fpath.exists():
            _print_file_preview(fpath)
        else:
            print(f"  WARNING: {fname} not found in output folder.")

    trace_path = outdir / "audit_trace.json"
    if trace_path.exists():
        with open(trace_path, encoding="utf-8") as f:
            trace = json.load(f)
        _banner("Provenance Summary")
        print(f"  Total symbols emitted : {trace['total_symbols']}")
        addr_syms = [s for s in trace["symbols"] if s["kind"] == "register_address"]
        print(f"  Register addresses    : {len(addr_syms)}")
        for s in addr_syms:
            print(f"    {s['symbol']:<50s} = {s['value_hex']}")
            print(f"      source : {s['source_file']}  page {s['source_page_id']}")
            print(f"      proof  : {s['provenance_note']}")
        print(f"\n  All symbols validated : PASS")
        print(f"  Artifacts saved to    : {outdir}")

    _banner("Demo complete")


def run_replay():
    _banner("KarcinoJen Demo — REPLAY mode (deterministic)")
    print(f"  Source : {DEMO_REPLAY}")
    print(f"  Note   : Showing pre-saved artifacts — no API calls needed.\n")

    required = ["input_validated.json", "expected_driver.h",
                "expected_driver.c", "expected_audit_trace.json"]
    for fname in required:
        fpath = DEMO_REPLAY / fname
        if not fpath.exists():
            print(f"[demo] ERROR: replay file missing: {fpath}", file=sys.stderr)
            print("       Run live mode once first to generate the replay bundle.",
                  file=sys.stderr)
            sys.exit(1)

    with open(DEMO_REPLAY / "input_validated.json", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    print(f"[demo] Replay input — {len(data)} validated register(s):")
    for reg in data:
        print(f"       • {reg['peripheral']}/{reg['register_name']}  "
              f"status={reg.get('validation_status')}  "
              f"attempts={reg.get('validation_attempts')}")

    _banner("Pre-verified Artifacts")
    for label, fname in [
        ("driver.h",         "expected_driver.h"),
        ("driver.c",         "expected_driver.c"),
        ("audit_trace.json", "expected_audit_trace.json"),
    ]:
        _print_file_preview(DEMO_REPLAY / fname)

    with open(DEMO_REPLAY / "expected_audit_trace.json", encoding="utf-8") as f:
        trace = json.load(f)
    _banner("Provenance Summary")
    print(f"  Total symbols : {trace['total_symbols']}")
    addr_syms = [s for s in trace["symbols"] if s["kind"] == "register_address"]
    for s in addr_syms:
        print(f"  {s['symbol']:<50s} = {s['value_hex']}")
        print(f"    source : {s['source_file']}  page {s['source_page_id']}")
        print(f"    proof  : {s['provenance_note']}")

    _banner("Replay complete")


def main():
    parser = argparse.ArgumentParser(description="KarcinoJen C2 Demo Runner")
    parser.add_argument("--input",  type=Path, default=None,
                        help="Path to validated JSON (live mode)")
    parser.add_argument("--out",    type=Path, default=None,
                        help="Output folder (live mode, auto-timestamped if omitted)")
    parser.add_argument("--replay", action="store_true",
                        help="Deterministic replay mode from demo_replay/")
    args = parser.parse_args()

    if args.replay:
        run_replay()
    else:
        input_path = args.input or FIXTURE
        if not input_path.exists():
            print(f"[demo] ERROR: input not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        outdir = args.out or (PROJECT_ROOT / "runs" / f"demo_{timestamp}")
        outdir.mkdir(parents=True, exist_ok=True)
        run_live(input_path, outdir)


if __name__ == "__main__":
    main()