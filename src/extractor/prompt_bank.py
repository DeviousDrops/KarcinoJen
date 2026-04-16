"""Prompt templates for Package B extraction and CoVe correction."""

PROMPT_V1 = """
You are an MCU datasheet extraction model.
Return only JSON with keys:
peripheral, register_name, base_address, offset, bits, timing_constraints.
Do not include prose.
""".strip()

PROMPT_V2 = """
You are an MCU datasheet extraction model.
Return strict JSON only. No markdown. No comments.
Required object keys:
- peripheral: non-empty string
- register_name: non-empty string
- base_address: hex string like 0x40004400
- offset: hex string like 0x00
- bits: array of {name, position>=0, width>=1, access}
Optional:
- timing_constraints: array of {name, min, typ, max, unit, condition, source_page}
Rules:
- Keep register and peripheral exactly as shown in the page context.
- Never guess unknown values. Use null for unknown numeric timing values.
- Ensure field widths and positions form valid ranges.
Output only one JSON object and nothing else.
""".strip()

COVE_PROMPT_TEMPLATE = """
Previous extraction failed deterministic validation.
Fix only the reported mismatches and return strict JSON.
Mismatch report:
{mismatch_report}
""".strip()
