import unittest

from src.extractor.schema_harness import validate_register_extraction


class TestSchemaHarness(unittest.TestCase):
    def test_valid_payload_passes(self) -> None:
        payload = {
            "peripheral": "USART2",
            "register_name": "USART_CR1",
            "base_address": "0x40004400",
            "offset": "0x00",
            "bits": [{"name": "UE", "position": 0, "width": 1, "access": "RW"}],
        }

        result = validate_register_extraction(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_invalid_payload_fails(self) -> None:
        payload = {
            "peripheral": "USART2",
            "register_name": "USART_CR1",
            "base_address": "40004400",
            "offset": "0x00",
            "bits": "bad",
        }

        result = validate_register_extraction(payload)
        self.assertFalse(result.is_valid)
        self.assertGreaterEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
