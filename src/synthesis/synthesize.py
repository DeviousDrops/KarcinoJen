#!/usr/bin/env python3
"""
synthesize.py  —  KarcinoJen Package C, Module C1
Reads one or more validated JSON files and emits:
  • driver.h          — #define macros for every register address and bit-field
  • driver.c          — init / read / write stubs for every register
  • audit_trace.json  — provenance record for every emitted symbol

Usage:
    python src/synthesis/synthesize.py \
        --input  tests/fixtures/validated_stm32l4.json \
        --outdir runs/c1_smoke/

    # multiple input files
    python src/synthesis/synthesize.py \
        --input  data/validated/usart2.json data/validated/gpioa.json \
        --outdir runs/c1_smoke/
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_hex(value: str) -> int:
    """Accept '0x40004400' or plain int strings."""
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value, 0)


def _bitmask(position: int, width: int) -> int:
    return ((1 << width) - 1) << position


def _macro_prefix(peripheral: str, register_name: str) -> str:
    """Build a safe C macro prefix, e.g. USART2_CR1"""
    p = peripheral.upper().replace(" ", "_")
    r = register_name.upper().replace(" ", "_")
    r_stripped = r
    for part in p.split("_"):
        if r_stripped.startswith(part + "_"):
            r_stripped = r_stripped[len(part) + 1:]
            break
    return f"{p}_{r_stripped}"


def _guard_name(path: str) -> str:
    return Path(path).name.upper().replace(".", "_").replace("-", "_")


# ── per-register synthesis ───────────────────────────────────────────────────

def _synthesize_register(reg: dict) -> dict:
    """
    Returns a dict with:
      symbols  — list of {name, value_int, value_hex, kind, provenance_note}
      h_lines  — list of C preprocessor lines for driver.h
      c_lines  — list of C function lines for driver.c
    """
    if reg.get("validation_status", "FAIL") != "PASS":
        return None  # hard fail-closed: never synthesize from unvalidated JSON

    peripheral   = reg["peripheral"]
    reg_name     = reg["register_name"]
    base_addr    = _parse_hex(reg["base_address"])
    offset       = _parse_hex(reg["offset"])
    full_addr    = base_addr + offset
    source_page  = reg.get("source_page_id", "unknown")
    source_file  = reg.get("source_file",    "unknown")
    val_attempts = reg.get("validation_attempts", 1)
    mcu_family   = reg.get("mcu_family", "unknown")
    prefix       = _macro_prefix(peripheral, reg_name)

    symbols = []
    h_lines = []
    c_lines = []

    # ── header comment ──────────────────────────────────────────────────────
    h_lines.append(f"/* {'-'*70}")
    h_lines.append(f" * Peripheral : {peripheral}")
    h_lines.append(f" * Register   : {reg_name}")
    h_lines.append(f" * MCU Family : {mcu_family}")
    h_lines.append(f" * Source     : {source_file}  page-id: {source_page}")
    h_lines.append(f" * Validated  : PASS  (attempts: {val_attempts})")
    h_lines.append(f" * {'-'*70} */")

    # ── address macro ───────────────────────────────────────────────────────
    addr_macro = f"{prefix}_ADDR"
    addr_hex   = f"0x{full_addr:08X}UL"
    h_lines.append(f"#define {addr_macro:<48s} {addr_hex}")
    symbols.append({
        "symbol":            addr_macro,
        "value_hex":         addr_hex,
        "kind":              "register_address",
        "peripheral":        peripheral,
        "register_name":     reg_name,
        "base_address":      reg["base_address"],
        "offset":            reg["offset"],
        "source_page_id":    source_page,
        "source_file":       source_file,
        "validation_status": "PASS",
        "validation_attempts": val_attempts,
        "provenance_note":   f"base_address({reg['base_address']}) + offset({reg['offset']})"
    })

    # ── bit-field macros ────────────────────────────────────────────────────
    for bit in reg.get("bits", []):
        name     = bit["name"].upper()
        pos      = int(bit["position"])
        width    = int(bit["width"])
        access   = bit.get("access", "RW")
        mask_val = _bitmask(pos, width)

        pos_macro  = f"{prefix}_{name}_POS"
        mask_macro = f"{prefix}_{name}_MASK"
        pos_hex    = f"{pos}U"
        mask_hex   = f"0x{mask_val:08X}UL"

        h_lines.append(f"#define {pos_macro:<48s} {pos_hex}   /* {access} | width={width} */")
        h_lines.append(f"#define {mask_macro:<48s} {mask_hex}")

        for sym_name, sym_val, kind, note in [
            (pos_macro,  pos_hex,  "bit_position", f"bit position {pos} for field {name}"),
            (mask_macro, mask_hex, "bit_mask",      f"((1<<{width})-1)<<{pos} for field {name}"),
        ]:
            symbols.append({
                "symbol":            sym_name,
                "value_hex":         sym_val,
                "kind":              kind,
                "peripheral":        peripheral,
                "register_name":     reg_name,
                "bit_field":         name,
                "bit_position":      pos,
                "bit_width":         width,
                "bit_access":        access,
                "source_page_id":    source_page,
                "source_file":       source_file,
                "validation_status": "PASS",
                "validation_attempts": val_attempts,
                "provenance_note":   note
            })

    h_lines.append("")  # blank line between registers

    # ── driver.c function stubs ─────────────────────────────────────────────
    fn_base = prefix.lower()
    c_lines.append(f"/* {peripheral} — {reg_name} */")
    c_lines.append(f"void {fn_base}_init(void) {{")
    c_lines.append(f"    /* TODO: configure {reg_name} for your application */")
    c_lines.append(f"}}")
    c_lines.append(f"")
    c_lines.append(f"uint32_t {fn_base}_read(void) {{")
    c_lines.append(f"    return *((volatile uint32_t *){addr_macro});")
    c_lines.append(f"}}")
    c_lines.append(f"")
    c_lines.append(f"void {fn_base}_write(uint32_t val) {{")
    c_lines.append(f"    *((volatile uint32_t *){addr_macro}) = val;")
    c_lines.append(f"}}")
    c_lines.append(f"")

    return {"symbols": symbols, "h_lines": h_lines, "c_lines": c_lines}


# ── file writers ─────────────────────────────────────────────────────────────

def _write_driver_h(all_results: list, outpath: str):
    guard = _guard_name(outpath)
    lines = []
    lines.append(f"/* AUTO-GENERATED by KarcinoJen synthesize.py — DO NOT EDIT */")
    lines.append(f"/* Generated: {datetime.now(timezone.utc).isoformat()} */")
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}")
    lines.append(f"")
    lines.append(f"#include <stdint.h>")
    lines.append(f"")
    lines.append(f"/* ── Register Addresses and Bit-Field Macros ─────── */")
    lines.append(f"")

    for r in all_results:
        lines.extend(r["h_lines"])

    lines.append(f"/* ── Function Declarations ──────────────────────── */")
    lines.append(f"")
    for r in all_results:
        for cl in r["c_lines"]:
            if cl.startswith("void ") and "_init" in cl:
                fn_base = cl.split("void ")[1].split("_init")[0]
                lines.append(f"void     {fn_base}_init(void);")
                lines.append(f"uint32_t {fn_base}_read(void);")
                lines.append(f"void     {fn_base}_write(uint32_t val);")
                lines.append(f"")
                break

    lines.append(f"#endif /* {guard} */")
    lines.append(f"")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_driver_c(all_results: list, h_filename: str, outpath: str):
    lines = []
    lines.append(f"/* AUTO-GENERATED by KarcinoJen synthesize.py — DO NOT EDIT */")
    lines.append(f"/* Generated: {datetime.now(timezone.utc).isoformat()} */")
    lines.append(f'#include "{h_filename}"')
    lines.append(f"")
    for r in all_results:
        lines.extend(r["c_lines"])

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_audit_trace(all_results: list, input_files: list, outpath: str):
    all_symbols = []
    for r in all_results:
        all_symbols.extend(r["symbols"])

    trace = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "generator":     "KarcinoJen synthesize.py — Package C Module C1",
        "input_files":   input_files,
        "total_symbols": len(all_symbols),
        "symbols":       all_symbols
    }
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="KarcinoJen C1 Synthesis")
    parser.add_argument("--input",  nargs="+", required=True,
                        help="Path(s) to validated JSON file(s)")
    parser.add_argument("--outdir", required=True,
                        help="Output directory")
    parser.add_argument("--audit-trace", action="store_true",
                        help="Write audit_trace.json alongside driver.h and driver.c")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    outdir = Path(args.outdir)

    all_registers = []
    loaded_files  = []
    for path in args.input:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        all_registers.extend(data)
        loaded_files.append(path)
        print(f"[synthesize] loaded {len(data)} register(s) from {path}")

    all_results = []
    skipped = 0
    for reg in all_registers:
        result = _synthesize_register(reg)
        if result is None:
            print(f"[synthesize] SKIP: {reg.get('peripheral')}/{reg.get('register_name')} "
                  f"status={reg.get('validation_status')}", file=sys.stderr)
            skipped += 1
        else:
            all_results.append(result)

    if not all_results:
        print("[synthesize] ERROR: no validated registers. Exiting.", file=sys.stderr)
        sys.exit(1)

    h_path     = outdir / "driver.h"
    c_path     = outdir / "driver.c"
    trace_path = outdir / "audit_trace.json"

    _write_driver_h(all_results, str(h_path))
    _write_driver_c(all_results, "driver.h", str(c_path))
    if args.audit_trace:
        _write_audit_trace(all_results, loaded_files, str(trace_path))

    total_syms = sum(len(r["symbols"]) for r in all_results)
    print(f"[synthesize] done.")
    print(f"  registers synthesized : {len(all_results)}")
    print(f"  registers skipped     : {skipped}")
    print(f"  symbols emitted       : {total_syms}")
    print(f"  driver.h              : {h_path}")
    print(f"  driver.c              : {c_path}")
    if args.audit_trace:
        print(f"  audit_trace.json      : {trace_path}")


if __name__ == "__main__":
    main()