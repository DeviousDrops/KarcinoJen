"""Hybrid retrieval with ColPali MaxSim and lexical fallback.

Supported backends:
- colpali: ColPali MaxSim late-interaction + lexical fusion
- lexical: local token overlap scorer

Fallback policy is intentionally simple and deterministic:
colpali -> lexical
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

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


def _extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
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


def _retrieve_colpali(
    *,
    query: str,
    datasheet_path: Path,
    retrieval_cfg: Any,
    top_k: int,
) -> list[dict[str, Any]] | None:
    try:
        from src.retrieval.colpali_retriever import ColPaliRetriever
    except ImportError:
        return None

    colpali_model = str(getattr(retrieval_cfg, "colpali_model", "vidore/colpali-v1.3-merged"))
    colpali_index_path = str(getattr(retrieval_cfg, "colpali_index_path", "data/colpali_index"))

    root = Path(__file__).resolve().parents[2]
    if not Path(colpali_index_path).is_absolute():
        colpali_index_path = str(root / colpali_index_path)

    try:
        retriever = ColPaliRetriever(
            colpali_model=colpali_model,
            index_root=colpali_index_path,
        )
        results = retriever.retrieve(
            query=query,
            datasheet_path=datasheet_path,
            top_k=top_k,
            lexical_weight=float(getattr(retrieval_cfg, "lexical_weight", 0.35)),
            semantic_weight=float(getattr(retrieval_cfg, "semantic_weight", 0.65)),
            hex_token_boost=float(getattr(retrieval_cfg, "hex_token_boost", 2.0)),
            rrf_k=int(getattr(retrieval_cfg, "rrf_k", 60)),
        )
        if results:
            return results
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("ColPali retrieval failed (%s), falling back to lexical", exc)

    return None


def retrieve_top_pages(
    *,
    query: str,
    datasheet_path: Path,
    retrieval_cfg: Any,
) -> list[dict[str, Any]]:
    """Retrieve top pages using configured backend.

    Backends:
    - colpali: ColPali MaxSim + lexical fusion
    - lexical: token-overlap lexical ranking

    Fallback: colpali -> lexical
    """

    hex_boost = float(getattr(retrieval_cfg, "hex_token_boost", 2.0))
    top_k = max(1, int(getattr(retrieval_cfg, "top_k", 3)))
    backend = str(getattr(retrieval_cfg, "backend", "colpali")).lower()

    if backend == "colpali":
        colpali_results = _retrieve_colpali(
            query=query,
            datasheet_path=datasheet_path,
            retrieval_cfg=retrieval_cfg,
            top_k=top_k,
        )
        if colpali_results:
            return colpali_results

    pages = _extract_pdf_pages(datasheet_path)
    if not pages:
        return []

    for page in pages:
        page["lexical_score"] = _lexical_score(query, str(page.get("text", "")), hex_boost)

    lexical_ranked = sorted(
        pages,
        key=lambda item: float(item.get("lexical_score", 0.0)),
        reverse=True,
    )
    return lexical_ranked[:top_k]
