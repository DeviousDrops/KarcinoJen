#!/usr/bin/env python3
"""Auto-generate MCU-Bench benchmark dataset from SVD ground truth.

Produces data/mcu-bench/benchmark.json with 15-20 records, each containing:
- id, mcu_family, query, peripheral, register, ground_truth_json

Ground truth is extracted directly from CMSIS-SVD XML files, ensuring
correctness by construction.

Usage:
    python scripts/generate_mcu_bench.py
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SVD_DIR = ROOT / "data" / "svd"
BENCH_DIR = ROOT / "data" / "mcu-bench"

# ── Register selections for benchmarking ─────────────────────────────────────
# (svd_stem, peripheral, register, query_template, datasheet_stem)

BENCHMARK_SPEC = [
    # ── STM32F401 ──
    ("stm32f401", "GPIOA", "MODER",
     "Extract GPIOA MODER register bit layout with mode encoding for each pin.",
     "stm32f401-rm"),
    ("stm32f401", "GPIOA", "ODR",
     "Extract GPIOA ODR output data register bit positions and widths.",
     "stm32f401-rm"),
    ("stm32f401", "GPIOB", "MODER",
     "Extract GPIOB MODER register base address, offset, and mode field widths.",
     "stm32f401-rm"),
    ("stm32f401", "USART2", "CR1",
     "Extract USART2 CR1 control register bits UE, M, PCE, TE, RE with positions.",
     "stm32f401-rm"),
    ("stm32f401", "USART2", "BRR",
     "Extract USART2 BRR baud rate register DIV_Mantissa and DIV_Fraction fields.",
     "stm32f401-rm"),
    ("stm32f401", "RCC", "AHB1ENR",
     "Extract RCC AHB1ENR register GPIOAEN and GPIOBEN clock enable bit positions.",
     "stm32f401-rm"),
    ("stm32f401", "RCC", "APB1ENR",
     "Extract RCC APB1ENR register with USART2EN and TIM2EN clock enable bits.",
     "stm32f401-rm"),
    ("stm32f401", "TIM2", "CR1",
     "Extract TIM2 CR1 register CEN, UDIS, URS, OPM, DIR bits with positions.",
     "stm32f401-rm"),
    ("stm32f401", "TIM2", "PSC",
     "Extract TIM2 PSC prescaler register bit layout and width.",
     "stm32f401-rm"),
    ("stm32f401", "SPI1", "CR1",
     "Extract SPI1 CR1 register SPE, BR, MSTR, CPOL, CPHA bits with positions.",
     "stm32f401-rm"),
    ("stm32f401", "I2C1", "CR1",
     "Extract I2C1 CR1 register PE, START, STOP, ACK bits with positions.",
     "stm32f401-rm"),
    ("stm32f401", "ADC1", "CR1",
     "Extract ADC1 CR1 register RES, SCAN, EOCIE bits with positions.",
     "stm32f401-rm"),
    ("stm32f401", "EXTI", "IMR",
     "Extract EXTI IMR interrupt mask register bit layout for lines 0 to 15.",
     "stm32f401-rm"),
    ("stm32f401", "SYSCFG", "EXTICR1",
     "Extract SYSCFG EXTICR1 register EXTI0 to EXTI3 field positions and widths.",
     "stm32f401-rm"),
    # ── RP2040 ──
    ("RP2040", "SIO", "GPIO_OUT",
     "Extract SIO GPIO_OUT register base address, offset, and bit layout for output.",
     "RP2040-datasheet"),
    ("RP2040", "SIO", "GPIO_OE",
     "Extract SIO GPIO_OE output enable register base address and bit layout.",
     "RP2040-datasheet"),
    ("RP2040", "UART0", "UARTDR",
     "Extract UART0 UARTDR data register bit fields including DATA and error flags.",
     "RP2040-datasheet"),
    ("RP2040", "TIMER", "TIMEHR",
     "Extract TIMER TIMEHR high bits register address and bit layout.",
     "RP2040-datasheet"),
    ("RP2040", "RESETS", "RESET",
     "Extract RESETS RESET register with peripheral reset control bit positions.",
     "RP2040-datasheet"),
]


def _parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text, 0)


def _extract_register_fields(register_elem: ET.Element) -> list[dict]:
    """Extract bit fields from an SVD register element."""
    fields = []
    for field_elem in register_elem.findall(".//field"):
        name = field_elem.findtext("name", "")
        bit_offset = field_elem.findtext("bitOffset")
        bit_width = field_elem.findtext("bitWidth")
        access = field_elem.findtext("access", "read-write")

        if bit_offset is None or bit_width is None:
            # Try bitRange format [msb:lsb]
            bit_range = field_elem.findtext("bitRange", "")
            if bit_range:
                import re
                match = re.match(r"\[(\d+):(\d+)]", bit_range)
                if match:
                    msb = int(match.group(1))
                    lsb = int(match.group(2))
                    bit_offset = str(lsb)
                    bit_width = str(msb - lsb + 1)

        if bit_offset is None or bit_width is None:
            continue

        # Normalize access strings
        access_map = {
            "read-write": "RW",
            "read-only": "RO",
            "write-only": "WO",
            "writeOnce": "WO",
            "read-writeOnce": "RW",
        }
        access_norm = access_map.get(access, "RW")

        fields.append({
            "name": name,
            "position": _parse_int(bit_offset),
            "width": _parse_int(bit_width),
            "access": access_norm,
        })

    # Sort by position
    fields.sort(key=lambda f: f["position"])
    return fields


def generate_ground_truth(
    svd_path: Path,
    peripheral_name: str,
    register_name: str,
) -> dict | None:
    """Generate ground truth JSON for a specific register from SVD."""
    tree = ET.parse(svd_path)
    root = tree.getroot()

    for periph in root.findall(".//peripheral"):
        p_name = periph.findtext("name", "")
        if p_name.upper() != peripheral_name.upper():
            continue

        base_addr_text = periph.findtext("baseAddress", "0x0")
        base_addr = _parse_int(base_addr_text)

        for reg in periph.findall(".//register"):
            r_name = reg.findtext("name", "")
            if r_name.upper() != register_name.upper():
                continue

            offset_text = reg.findtext("addressOffset", "0x0")
            offset = _parse_int(offset_text)
            size = _parse_int(reg.findtext("size", "32"))

            fields = _extract_register_fields(reg)

            return {
                "peripheral": p_name,
                "register_name": r_name,
                "base_address": f"0x{base_addr:08X}",
                "offset": f"0x{offset:02X}",
                "register_size": size,
                "bits": fields,
                "timing_constraints": [],
            }

    return None


def main():
    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    skipped = []

    for idx, (svd_stem, periph, reg, query, ds_stem) in enumerate(BENCHMARK_SPEC, 1):
        bench_id = f"mcu_bench_{idx:03d}"
        svd_path = SVD_DIR / f"{svd_stem}.svd"

        if not svd_path.exists():
            print(f"  SKIP {bench_id}: SVD file not found: {svd_path.name}")
            skipped.append(bench_id)
            continue

        gt = generate_ground_truth(svd_path, periph, reg)
        if gt is None:
            print(f"  SKIP {bench_id}: Register {periph}.{reg} not found in {svd_path.name}")
            skipped.append(bench_id)
            continue

        record = {
            "id": bench_id,
            "mcu_family": svd_stem.upper(),
            "query": query,
            "peripheral": periph,
            "register": reg,
            "datasheet_stem": ds_stem,
            "svd_stem": svd_stem,
            "page_image": None,
            "ground_truth_json": gt,
            "ground_truth": gt,
        }
        records.append(record)
        print(f"  [{bench_id}] {periph}.{reg} — {len(gt['bits'])} fields, "
              f"addr=0x{_parse_int(gt['base_address']) + _parse_int(gt['offset']):08X}")

    # Write benchmark file
    benchmark = {
        "name": "MCU-Bench",
        "version": "1.0",
        "description": "Auto-generated benchmark dataset for KarcinoJen evaluation",
        "total_records": len(records),
        "mcu_families": sorted(set(r["mcu_family"] for r in records)),
        "records": records,
    }

    output_path = BENCH_DIR / "benchmark.json"
    output_path.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")

    # Also write individual ground truth files
    gt_dir = BENCH_DIR / "ground_truth"
    gt_dir.mkdir(exist_ok=True)
    for record in records:
        gt_path = gt_dir / f"{record['id']}.json"
        gt_path.write_text(json.dumps(record["ground_truth"], indent=2), encoding="utf-8")

    print(f"\nMCU-Bench generated: {output_path}")
    print(f"  Total records: {len(records)}")
    print(f"  Skipped: {len(skipped)}")
    print(f"  Ground truth dir: {gt_dir}")


if __name__ == "__main__":
    main()
