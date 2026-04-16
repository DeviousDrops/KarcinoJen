"""Hybrid retrieval with Chroma semantic search plus lexical scoring fallback."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from src.index.chroma_indexer import extract_pdf_pages, upsert_pdf_pages_to_chroma

ROOT = Path(__file__).resolve().parents[2]

HEX_PATTERN = re.compile(r"0x[0-9a-fA-F]+")


def _tokenize(text: str) -> list[str]:
    clean = re.sub(r"[^a-zA-Z0-9_]+", " ", text.lower())
    return [token for token in clean.split() if token]


def _lexical_score(query: str, page_text: str, hex_token_boost: float) -> float:
    query_tokens = _tokenize(query)
    page_tokens = _tokenize(page_text)
    if not query_tokens or not page_tokens:
        return 0.0

    page_tf: dict[str, int] = {}
    for token in page_tokens:
        page_tf[token] = page_tf.get(token, 0) + 1

    score = 0.0
    for token in query_tokens:
        tf = page_tf.get(token, 0)
        if tf:
            score += 1.0 + math.log(1 + tf)

    for hex_token in HEX_PATTERN.findall(query):
        if hex_token.lower() in page_text.lower():
            score += hex_token_boost

    return score


def _rrf_fuse(
    semantic_ranked: list[str],
    lexical_ranked: list[str],
    *,
    rrf_k: int,
    semantic_weight: float,
    lexical_weight: float,
) -> dict[str, float]:
    fused: dict[str, float] = {}

    for rank, page_id in enumerate(semantic_ranked, start=1):
        fused[page_id] = fused.get(page_id, 0.0) + (semantic_weight / (rrf_k + rank))

    for rank, page_id in enumerate(lexical_ranked, start=1):
        fused[page_id] = fused.get(page_id, 0.0) + (lexical_weight / (rrf_k + rank))

    return fused


def retrieve_top_pages(
    *,
    query: str,
    datasheet_path: Path,
    retrieval_cfg: Any,
) -> list[dict[str, Any]]:
    """Retrieve top pages from a datasheet using configured backend.

    Backends:
    - lexical: local token overlap scorer
    - chroma: Chroma semantic retrieval + lexical fusion (falls back to lexical)
    """
    pages = extract_pdf_pages(datasheet_path)
    if not pages:
        return []

    hex_boost = float(getattr(retrieval_cfg, "hex_token_boost", 2.0))
    top_k = max(1, int(getattr(retrieval_cfg, "top_k", 3)))

    for page in pages:
        page["lexical_score"] = _lexical_score(query, str(page.get("text", "")), hex_boost)

    lexical_ranked = sorted(
        pages,
        key=lambda item: float(item.get("lexical_score", 0.0)),
        reverse=True,
    )

    backend = str(getattr(retrieval_cfg, "backend", "lexical")).lower()
    if backend != "chroma":
        return lexical_ranked[:top_k]

    try:
        import chromadb  # type: ignore
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # type: ignore
    except ImportError:
        # Dependency is optional; use lexical retrieval instead.
        return lexical_ranked[:top_k]

    chroma_path = Path(str(getattr(retrieval_cfg, "chroma_path", "data/chroma")))
    if not chroma_path.is_absolute():
        chroma_path = ROOT / chroma_path

    collection_prefix = str(getattr(retrieval_cfg, "collection_prefix", "datasheet_pages"))
    collection_name = f"{collection_prefix}_{datasheet_path.stem.lower()}"
    embedding_model = str(
        getattr(retrieval_cfg, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    )

    # Keep indexing idempotent by upserting page IDs on each run.
    upsert_pdf_pages_to_chroma(
        pdf_path=datasheet_path,
        chroma_path=chroma_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
    )

    client = chromadb.PersistentClient(path=str(chroma_path))
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    candidate_multiplier = max(2, int(getattr(retrieval_cfg, "semantic_candidates_multiplier", 5)))
    n_results = min(len(pages), max(top_k, top_k * candidate_multiplier))
    semantic_results = collection.query(query_texts=[query], n_results=n_results)
    semantic_ids = [str(page_id) for page_id in semantic_results.get("ids", [[]])[0]]

    lexical_ids = [str(page["page_id"]) for page in lexical_ranked[:n_results]]
    fused = _rrf_fuse(
        semantic_ids,
        lexical_ids,
        rrf_k=int(getattr(retrieval_cfg, "rrf_k", 60)),
        semantic_weight=float(getattr(retrieval_cfg, "semantic_weight", 0.45)),
        lexical_weight=float(getattr(retrieval_cfg, "lexical_weight", 0.55)),
    )

    page_map = {str(page["page_id"]): page for page in pages}
    ranked_ids = sorted(fused.keys(), key=lambda item: fused[item], reverse=True)

    top_pages: list[dict[str, Any]] = []
    for page_id in ranked_ids[:top_k]:
        page = dict(page_map[page_id])
        page["score"] = fused[page_id]
        top_pages.append(page)

    if top_pages:
        return top_pages

    return lexical_ranked[:top_k]
