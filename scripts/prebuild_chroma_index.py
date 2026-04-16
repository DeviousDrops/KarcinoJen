"""Prebuild Chroma index for all datasheets in data/datasheets."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import load_runtime_config
from src.index.chroma_indexer import upsert_pdf_pages_to_chroma

CONFIG_PATH = ROOT / "configs" / "model_config.json"
DATASHEET_DIR = ROOT / "data" / "datasheets"


def main() -> None:
    runtime_cfg = load_runtime_config(CONFIG_PATH)
    retrieval_cfg = runtime_cfg.retrieval

    pdfs = sorted(
        [
            path
            for path in DATASHEET_DIR.glob("*.pdf")
            if path.is_file()
        ]
    )
    if not pdfs:
        raise RuntimeError(f"No datasheets found under: {DATASHEET_DIR}")

    chroma_path = Path(retrieval_cfg.chroma_path)
    if not chroma_path.is_absolute():
        chroma_path = ROOT / chroma_path

    total_pages = 0
    print(f"Chroma path: {chroma_path}")
    print(f"Embedding model: {retrieval_cfg.embedding_model}")

    for pdf_path in pdfs:
        collection_name = f"{retrieval_cfg.collection_prefix}_{pdf_path.stem.lower()}"
        pages = upsert_pdf_pages_to_chroma(
            pdf_path=pdf_path,
            chroma_path=chroma_path,
            collection_name=collection_name,
            embedding_model=retrieval_cfg.embedding_model,
        )
        total_pages += len(pages)
        print(f"Indexed {len(pages):4d} pages | {pdf_path.name} | collection={collection_name}")

    print(f"Done. Indexed {len(pdfs)} datasheets and {total_pages} total pages.")


if __name__ == "__main__":
    main()
