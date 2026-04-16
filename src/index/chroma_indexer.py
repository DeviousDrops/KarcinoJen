"""Chroma indexing helpers for datasheet pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract plain text from all PDF pages for retrieval indexing."""
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to read datasheet pages") from exc

    pages: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as document:
        for index in range(len(document)):
            page = document.load_page(index)
            text = page.get_text("text") or ""
            pages.append(
                {
                    "page_id": f"{pdf_path.stem}_p{index + 1}",
                    "source_file": pdf_path.name,
                    "page_number": index + 1,
                    "peripheral": pdf_path.stem,
                    "keywords": [],
                    "text": text,
                }
            )

    return pages


def upsert_pdf_pages_to_chroma(
    *,
    pdf_path: Path,
    chroma_path: Path,
    collection_name: str,
    embedding_model: str,
) -> list[dict[str, Any]]:
    """Index all page texts from a PDF into a Chroma collection."""
    try:
        import chromadb  # type: ignore
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Chroma indexing requires chromadb and sentence-transformers"
        ) from exc

    pages = extract_pdf_pages(pdf_path)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [str(page["page_id"]) for page in pages]
    docs = [str(page["text"]) for page in pages]
    metadatas = [
        {
            "source_file": str(page["source_file"]),
            "page_number": int(page["page_number"]),
            "peripheral": str(page["peripheral"]),
        }
        for page in pages
    ]

    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    return pages
