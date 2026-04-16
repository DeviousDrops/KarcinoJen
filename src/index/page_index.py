"""Page catalog indexing for retrieval runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class PageRecord:
    page_id: str
    source_file: str
    page_number: int
    mcu_family: str
    peripheral: str
    keywords: list[str]


def load_page_catalog(path: Path) -> list[PageRecord]:
    records: list[PageRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        records.append(
            PageRecord(
                page_id=str(payload["page_id"]),
                source_file=str(payload["source_file"]),
                page_number=int(payload["page_number"]),
                mcu_family=str(payload["mcu_family"]),
                peripheral=str(payload["peripheral"]),
                keywords=[str(keyword) for keyword in payload.get("keywords", [])],
            )
        )
    return records
