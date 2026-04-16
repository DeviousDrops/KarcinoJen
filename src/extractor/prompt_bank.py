"""Prompt templates for Package B extraction and CoVe correction."""

PROMPT_V1 = """
You are an MCU datasheet extraction model.
Return only JSON with keys:
peripheral, register_name, base_address, offset, bits, timing_constraints.
Do not include prose.
""".strip()

PROMPT_V2 = """
You are an MCU datasheet extraction model. Analyse the provided page images and text.
Return ONE strict JSON object only. No markdown. No prose. No extra keys.

Required keys (ALL must be present):
  peripheral      – string, e.g. "GPIOA"
  register_name   – string, e.g. "MODER"
  base_address    – hex string, e.g. "0x40020000"
  offset          – hex string offset from base, e.g. "0x00"   <-- REQUIRED, never omit
  bits            – array of objects, each with keys: name, position, width, access

Optional key:
  timing_constraints – array of {name, min, typ, max, unit, condition, source_page}

Rules:
  - Use register/peripheral names EXACTLY as they appear in the datasheet page.
  - base_address must be the peripheral's memory-mapped base, NOT the full register address.
  - offset is the register's byte offset from base_address.
  - bits[].position is zero-indexed bit position (integer >= 0).
  - bits[].width is number of bits (integer >= 1).
  - Never include overlapping bit ranges.
  - If a value is unknown, use null for numeric timing fields; never omit a required key.
  - Output ONLY the JSON object and nothing else.
""".strip()

COVE_PROMPT_TEMPLATE = """
You are an MCU datasheet extraction model.
Your previous extraction attempt FAILED validation. You must produce a CORRECTED extraction.

Validation failure report:
{mismatch_report}

You MUST return a new, corrected JSON object with ALL of these required keys:
  peripheral    – string
  register_name – string
  base_address  – hex string like 0x40020000
  offset        – hex string like 0x00
  bits          – array of objects each with: name (string), position (int>=0), width (int>=1), access (string)

Fix ONLY the reported issues. Keep correct fields unchanged.
Return ONLY the corrected JSON object and nothing else. No explanations. No markdown.
""".strip()
