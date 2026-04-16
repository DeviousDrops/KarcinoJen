import unittest
from pathlib import Path

from src.validator.svd_validator import load_svd_registers, validate_extraction


class TestSvdValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.registers = load_svd_registers(str(root / "data" / "svd" / "mock_mcu.svd"))

    def test_detects_address_drift(self) -> None:
        extraction = {
            "peripheral": "USART2",
            "register_name": "USART_CR1",
            "base_address": "0x40004800",
            "offset": "0x00",
            "bits": [{"name": "UE", "position": 0, "width": 1, "access": "RW"}],
        }

        result = validate_extraction(extraction, self.registers)
        self.assertEqual(result.status, "FAIL")
        self.assertFalse(result.checks["address_range"]["ok"])

    def test_detects_bit_overlap(self) -> None:
        extraction = {
            "peripheral": "USART2",
            "register_name": "USART_CR1",
            "base_address": "0x40004400",
            "offset": "0x00",
            "bits": [
                {"name": "A", "position": 0, "width": 4, "access": "RW"},
                {"name": "B", "position": 2, "width": 2, "access": "RW"},
            ],
        }

        result = validate_extraction(extraction, self.registers)
        self.assertEqual(result.status, "FAIL")
        self.assertFalse(result.checks["bit_arithmetic"]["ok"])


if __name__ == "__main__":
    unittest.main()
