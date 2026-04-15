#!/usr/bin/env python3
"""
Run: python -m pytest tests/test_synthesize.py -v
  or: python tests/test_synthesize.py
"""
import json, sys, os, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from synthesis.synthesize import (
    _parse_hex, _bitmask, _macro_prefix, _synthesize_register,
    _write_driver_h, _write_driver_c, _write_audit_trace,
)

VALID_REG = {
    "peripheral": "USART2", "register_name": "USART_CR1",
    "base_address": "0x40004400", "offset": "0x00",
    "bits": [
        {"name": "UE", "position": 0, "width": 1, "access": "RW"},
        {"name": "TE", "position": 3, "width": 1, "access": "RW"},
    ],
    "timing_constraints": [], "source_page_id": "stm32l4_rm0351_p1238",
    "source_file": "RM0351.pdf", "validation_status": "PASS",
    "validation_attempts": 1, "mcu_family": "STM32L4",
}
INVALID_REG   = {**VALID_REG, "validation_status": "FAIL"}
UNCERTAIN_REG = {**VALID_REG, "validation_status": "UNCERTAIN"}


class TestHelpers(unittest.TestCase):
    def test_parse_hex_string(self):
        self.assertEqual(_parse_hex("0x40004400"), 0x40004400)
    def test_parse_hex_zero_offset(self):
        self.assertEqual(_parse_hex("0x00"), 0)
    def test_parse_hex_decimal_string(self):
        self.assertEqual(_parse_hex("12"), 12)
    def test_bitmask_width1_pos0(self):
        self.assertEqual(_bitmask(0, 1), 0x1)
    def test_bitmask_width1_pos3(self):
        self.assertEqual(_bitmask(3, 1), 0x8)
    def test_bitmask_width2_pos2(self):
        self.assertEqual(_bitmask(2, 2), 0xC)
    def test_bitmask_width16_pos0(self):
        self.assertEqual(_bitmask(0, 16), 0xFFFF)
    def test_macro_prefix_basic(self):
        self.assertEqual(_macro_prefix("GPIOA", "GPIOA_MODER"), "GPIOA_MODER")
    def test_macro_prefix_no_match(self):
        self.assertEqual(_macro_prefix("TIM2", "ARR"), "TIM2_ARR")


class TestSynthesizeRegister(unittest.TestCase):
    def test_valid_register_returns_result(self):
        self.assertIsNotNone(_synthesize_register(VALID_REG))
    def test_fail_register_returns_none(self):
        self.assertIsNone(_synthesize_register(INVALID_REG))
    def test_uncertain_register_returns_none(self):
        self.assertIsNone(_synthesize_register(UNCERTAIN_REG))
    def test_address_symbol_present(self):
        result = _synthesize_register(VALID_REG)
        addr_syms = [s for s in result["symbols"] if s["kind"] == "register_address"]
        self.assertEqual(len(addr_syms), 1)
        self.assertEqual(addr_syms[0]["value_hex"], "0x40004400UL")
    def test_full_address_computed_correctly(self):
        reg = {**VALID_REG, "offset": "0x0C"}
        addr_syms = [s for s in _synthesize_register(reg)["symbols"] if s["kind"] == "register_address"]
        self.assertEqual(addr_syms[0]["value_hex"], "0x4000440CUL")
    def test_bit_masks_computed_correctly(self):
        result = _synthesize_register(VALID_REG)
        mask_syms = {s["symbol"]: s["value_hex"] for s in result["symbols"] if s["kind"] == "bit_mask"}
        ue_key = next(k for k in mask_syms if "UE_MASK" in k)
        te_key = next(k for k in mask_syms if "TE_MASK" in k)
        self.assertEqual(mask_syms[ue_key], "0x00000001UL")
        self.assertEqual(mask_syms[te_key], "0x00000008UL")
    def test_every_symbol_has_provenance(self):
        for sym in _synthesize_register(VALID_REG)["symbols"]:
            self.assertIn("source_page_id", sym)
            self.assertIn("provenance_note", sym)
            self.assertEqual(sym["validation_status"], "PASS")
    def test_h_lines_contain_addr_define(self):
        h_text = "\n".join(_synthesize_register(VALID_REG)["h_lines"])
        self.assertIn("0x40004400UL", h_text)
        self.assertIn("_ADDR", h_text)
    def test_c_lines_contain_read_write(self):
        c_text = "\n".join(_synthesize_register(VALID_REG)["c_lines"])
        self.assertIn("_read(void)", c_text)
        self.assertIn("_write(uint32_t val)", c_text)
        self.assertIn("volatile uint32_t", c_text)
    def test_no_synthesis_from_unvalidated(self):
        for status in ("FAIL", "UNCERTAIN", "PENDING", ""):
            self.assertIsNone(_synthesize_register({**VALID_REG, "validation_status": status}))
    def test_symbol_count(self):
        # 1 addr + 2 bits × 2 (pos+mask) = 5
        self.assertEqual(len(_synthesize_register(VALID_REG)["symbols"]), 5)


class TestFileWriters(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.result = _synthesize_register(VALID_REG)
    def test_driver_h_has_include_guard(self):
        path = os.path.join(self.tmpdir, "driver.h")
        _write_driver_h([self.result], path)
        content = open(path).read()
        self.assertIn("#ifndef DRIVER_H", content)
        self.assertIn("#endif", content)
    def test_driver_h_has_stdint(self):
        path = os.path.join(self.tmpdir, "driver.h")
        _write_driver_h([self.result], path)
        self.assertIn("#include <stdint.h>", open(path).read())
    def test_driver_c_includes_header(self):
        _write_driver_h([self.result], os.path.join(self.tmpdir, "driver.h"))
        c_path = os.path.join(self.tmpdir, "driver.c")
        _write_driver_c([self.result], "driver.h", c_path)
        self.assertIn('#include "driver.h"', open(c_path).read())
    def test_audit_trace_symbol_count(self):
        path = os.path.join(self.tmpdir, "audit_trace.json")
        _write_audit_trace([self.result], ["f.json"], path)
        trace = json.load(open(path))
        self.assertEqual(trace["total_symbols"], len(self.result["symbols"]))
    def test_audit_trace_required_keys(self):
        path = os.path.join(self.tmpdir, "audit_trace.json")
        _write_audit_trace([self.result], ["f.json"], path)
        required = {"symbol","value_hex","kind","source_page_id","validation_status","provenance_note"}
        for sym in json.load(open(path))["symbols"]:
            self.assertFalse(required - sym.keys())
    def test_audit_trace_is_valid_json(self):
        path = os.path.join(self.tmpdir, "audit_trace.json")
        _write_audit_trace([self.result], ["f.json"], path)
        self.assertIsInstance(json.load(open(path)), dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)