"""MaxSim late-interaction retriever using ColPali patch embeddings.

Implements the Stage 4 retrieval path from the architecture:
- Loads pre-built ColPali index (patch embeddings per page)
- Encodes query via ColPali
- Computes MaxSim: for each query token, find max similarity across all
  page patches, then sum across query tokens
- Returns ranked page candidates

Also provides the full hybrid retrieval with RRF fusion of
MaxSim (semantic/visual) + BM25-style lexical scoring.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

HEX_PATTERN = re.compile(r"0x[0-9a-fA-F]+")
ROOT = Path(__file__).resolve().parents[2]


def maxsim_score(query_emb: np.ndarray, page_emb: np.ndarray) -> float:
    """Compute MaxSim score between query and page embeddings.

    For each query token embedding, find its maximum cosine similarity
    with any page patch embedding, then sum across all query tokens.

    Args:
        query_emb: shape (num_query_tokens, dim)
        page_emb: shape (num_patches, dim)

    Returns:
        Scalar MaxSim score.
    """
    # Normalize embeddings for cosine similarity
    q_norm = query_emb / (np.linalg.norm(query_emb, axis=1, keepdims=True) + 1e-9)
    p_norm = page_emb / (np.linalg.norm(page_emb, axis=1, keepdims=True) + 1e-9)

    # Similarity matrix: (num_query_tokens, num_patches)
    sim_matrix = q_norm @ p_norm.T

    # MaxSim: max over patches for each query token, then sum
    max_sims = sim_matrix.max(axis=1)  # (num_query_tokens,)
    return float(max_sims.sum())


def _tokenize(text: str) -> list[str]:
    clean = re.sub(r"[^a-zA-Z0-9_]+", " ", text.lower())
    return [token for token in clean.split() if token]


def _lexical_score(query: str, page_text: str, hex_boost: float) -> float:
    """BM25-style lexical scoring with hex token boost."""
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
            score += hex_boost

    return score


def _rrf_fuse(
    rankings: list[tuple[str, list[str], float]],
    *,
    rrf_k: int = 60,
) -> dict[str, float]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    Args:
        rankings: list of (label, ranked_page_ids, weight) tuples
        rrf_k: smoothing constant

    Returns:
        dict mapping page_id to fused score
    """
    fused: dict[str, float] = {}
    for _label, ranked_ids, weight in rankings:
        for rank, page_id in enumerate(ranked_ids, start=1):
            fused[page_id] = fused.get(page_id, 0.0) + (weight / (rrf_k + rank))
    return fused


class ColPaliRetriever:
    """Hybrid retriever combining ColPali MaxSim with lexical scoring."""

    _disabled_stems: dict[str, str] = {}

    def __init__(
        self,
        colpali_model: str = "vidore/colpali-v1.3-merged",
        index_root: str | Path = "data/colpali_index",
        device: str | None = None,
    ):
        self._colpali_model = colpali_model
        self._index_root = Path(index_root)
        self._device = device
        self._indexer = None

    def _get_indexer(self):
        if self._indexer is None:
            from src.index.colpali_indexer import ColPaliIndexer
            self._indexer = ColPaliIndexer(
                model_name=self._colpali_model,
                index_root=self._index_root,
                device=self._device,
            )
        return self._indexer

    def retrieve(
        self,
        *,
        query: str,
        datasheet_path: Path,
        top_k: int = 5,
        lexical_weight: float = 0.35,
        semantic_weight: float = 0.65,
        hex_token_boost: float = 2.0,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Retrieve top-k pages using hybrid ColPali MaxSim + lexical fusion.

        If ColPali index doesn't exist, builds it first (offline step).
        Falls back to lexical-only if ColPali is unavailable.
        """
        datasheet_path = Path(datasheet_path).resolve()
        stem = datasheet_path.stem.lower()

        if stem in self._disabled_stems:
            logger.info(
                "ColPali disabled for %s in this run (%s); using lexical-only fallback.",
                stem,
                self._disabled_stems[stem],
            )
            return self._lexical_only_retrieval(query, datasheet_path, top_k, hex_token_boost)

        # Try to load or build ColPali index
        try:
            indexer = self._get_indexer()
            manifest = indexer.load_index(stem)
            if manifest is None:
                logger.info("No ColPali index found for %s, building now...", stem)
                manifest = indexer.index_datasheet(datasheet_path)
        except (ImportError, RuntimeError) as exc:
            self._disabled_stems[stem] = type(exc).__name__
            logger.warning("ColPali unavailable (%s), falling back to lexical-only", exc)
            return self._lexical_only_retrieval(query, datasheet_path, top_k, hex_token_boost)

        pages = manifest["pages"]
        if not pages:
            return []

        # Load page texts from PDF for lexical scoring
        page_texts = self._extract_page_texts(datasheet_path)

        # ── MaxSim path ──────────────────────────────────────────────────
        try:
            query_emb = indexer.encode_query(query)
        except Exception as exc:
            self._disabled_stems[stem] = type(exc).__name__
            logger.warning("ColPali query encoding failed (%s), lexical-only", exc)
            return self._lexical_only_retrieval(query, datasheet_path, top_k, hex_token_boost)

        maxsim_scores: list[tuple[str, float]] = []
        for page_meta in pages:
            page_id = page_meta["page_id"]
            emb_path = page_meta["embedding_path"]

            if not Path(emb_path).exists():
                continue

            page_emb = np.load(emb_path).astype(np.float32)
            score = maxsim_score(query_emb, page_emb)
            maxsim_scores.append((page_id, score))

        maxsim_scores.sort(key=lambda x: x[1], reverse=True)
        maxsim_ranked = [pid for pid, _ in maxsim_scores]

        # ── Lexical/BM25 path ────────────────────────────────────────────
        lexical_scores: list[tuple[str, float]] = []
        for page_meta in pages:
            page_id = page_meta["page_id"]
            page_number = page_meta["page_number"]
            text = page_texts.get(page_number, "")
            score = _lexical_score(query, text, hex_token_boost)
            lexical_scores.append((page_id, score))

        lexical_scores.sort(key=lambda x: x[1], reverse=True)
        lexical_ranked = [pid for pid, _ in lexical_scores]

        # ── RRF Fusion ───────────────────────────────────────────────────
        fused = _rrf_fuse(
            [
                ("maxsim", maxsim_ranked, semantic_weight),
                ("lexical", lexical_ranked, lexical_weight),
            ],
            rrf_k=rrf_k,
        )

        # Build result list with metadata
        page_map = {p["page_id"]: p for p in pages}
        ranked_ids = sorted(fused.keys(), key=lambda pid: fused[pid], reverse=True)

        results: list[dict[str, Any]] = []
        for page_id in ranked_ids[:top_k]:
            meta = page_map[page_id]
            page_number = meta["page_number"]
            results.append({
                "page_id": page_id,
                "source_file": meta["source_file"],
                "page_number": page_number,
                "peripheral": datasheet_path.stem,
                "keywords": [],
                "text": page_texts.get(page_number, ""),
                "image_path": meta["image_path"],
                "score": fused[page_id],
                "retrieval_method": "colpali_hybrid",
            })

        return results

    def _extract_page_texts(self, pdf_path: Path) -> dict[int, str]:
        """Extract text from all PDF pages, keyed by 1-based page number."""
        try:
            import fitz  # type: ignore
        except ImportError:
            return {}

        texts: dict[int, str] = {}
        with fitz.open(pdf_path) as doc:
            for idx in range(len(doc)):
                page = doc.load_page(idx)
                texts[idx + 1] = page.get_text("text") or ""
        return texts

    def _lexical_only_retrieval(
        self,
        query: str,
        datasheet_path: Path,
        top_k: int,
        hex_token_boost: float,
    ) -> list[dict[str, Any]]:
        """Lexical-only fallback when ColPali is unavailable."""
        page_texts = self._extract_page_texts(datasheet_path)
        stem = datasheet_path.stem.lower()

        scored: list[tuple[int, float]] = []
        for page_number, text in page_texts.items():
            score = _lexical_score(query, text, hex_token_boost)
            scored.append((page_number, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[dict[str, Any]] = []
        for page_number, score in scored[:top_k]:
            page_id = f"{stem}_p{page_number}"
            results.append({
                "page_id": page_id,
                "source_file": datasheet_path.name,
                "page_number": page_number,
                "peripheral": datasheet_path.stem,
                "keywords": [],
                "text": page_texts.get(page_number, ""),
                "image_path": None,
                "score": score,
                "retrieval_method": "lexical_fallback",
            })

        return results
