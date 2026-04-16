import unittest
from pathlib import Path

from src.orchestration.cove_loop import run_cove_loop
from src.validator.svd_validator import load_svd_registers


class TestCoVeLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.registers = load_svd_registers(str(root / "data" / "svd" / "mock_mcu.svd"))

    def test_cove_fixes_address_and_name(self) -> None:
        extraction = {
            "peripheral": "USART2",
            "register_name": "USART_CRI",
            "base_address": "0x40004800",
            "offset": "0x00",
            "bits": [{"name": "UE", "position": 0, "width": 1, "access": "RW"}],
        }

        outcome = run_cove_loop(extraction, self.registers, max_attempts=3)
        self.assertEqual(outcome.status, "PASS")
        self.assertLessEqual(len(outcome.attempts), 3)

    def test_cove_returns_uncertain_when_not_fixable(self) -> None:
        extraction = {
            "peripheral": "USART2",
            "register_name": "UNKNOWN_REG",
            "base_address": "0xZZZZ",
            "offset": "0x00",
            "bits": "unparseable",
        }

        outcome = run_cove_loop(extraction, self.registers, max_attempts=3)
        self.assertEqual(outcome.status, "UNCERTAIN")
        self.assertEqual(len(outcome.attempts), 3)


if __name__ == "__main__":
    unittest.main()
