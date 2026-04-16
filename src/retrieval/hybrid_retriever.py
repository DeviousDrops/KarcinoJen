"""Hybrid retrieval runtime (lexical + semantic + RRF fusion)."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from src.extractor.model_config import RetrievalConfig
from src.index.page_index import PageRecord

HEX_PATTERN = re.compile(r"0x[0-9a-fA-F]+")


@dataclass(frozen=True)
class RetrievalHit:
    page: PageRecord
    lexical_score: float
    semantic_score: float
    rrf_score: float


def _tokenize(text: str) -> list[str]:
    clean = re.sub(r"[^a-zA-Z0-9_]+", " ", text.lower())
    return [token for token in clean.split() if token]


def _lexical_score(query: str, page: PageRecord, cfg: RetrievalConfig) -> float:
    tokens = _tokenize(query)
    page_tokens = [token for kw in page.keywords for token in _tokenize(kw)]
    if not tokens or not page_tokens:
        return 0.0

    page_tf: dict[str, int] = {}
    for token in page_tokens:
        page_tf[token] = page_tf.get(token, 0) + 1

    score = 0.0
    for token in tokens:
        tf = page_tf.get(token, 0)
        if tf:
            score += 1.0 + math.log(1 + tf)

    query_hex = HEX_PATTERN.findall(query)
    if query_hex:
        keyword_text = " ".join(page.keywords).lower()
        for hex_token in query_hex:
            if hex_token.lower() in keyword_text:
                score += cfg.hex_token_boost

    return score


def _semantic_score(query: str, page: PageRecord) -> float:
    query_tokens = set(_tokenize(query))
    page_tokens = set(token for kw in page.keywords for token in _tokenize(kw))
    if not query_tokens or not page_tokens:
        return 0.0
    intersection = len(query_tokens & page_tokens)
    union = len(query_tokens | page_tokens)
    return intersection / union


def retrieve_top_k(query: str, pages: list[PageRecord], cfg: RetrievalConfig, top_k: int) -> list[RetrievalHit]:
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    lexical_ranked = sorted(
        pages,
        key=lambda page: _lexical_score(query, page, cfg),
        reverse=True,
    )
    semantic_ranked = sorted(
        pages,
        key=lambda page: _semantic_score(query, page),
        reverse=True,
    )

    lexical_index = {page.page_id: rank for rank, page in enumerate(lexical_ranked, start=1)}
    semantic_index = {page.page_id: rank for rank, page in enumerate(semantic_ranked, start=1)}

    hit_rows: list[RetrievalHit] = []
    for page in pages:
        lexical_score = _lexical_score(query, page, cfg)
        semantic_score = _semantic_score(query, page)
        rrf = (1.0 / (cfg.rrf_k + lexical_index[page.page_id])) + (
            1.0 / (cfg.rrf_k + semantic_index[page.page_id])
        )
        combined = (cfg.lexical_weight * lexical_score) + (cfg.semantic_weight * semantic_score) + rrf
        hit_rows.append(
            RetrievalHit(
                page=page,
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                rrf_score=combined,
            )
        )

    return sorted(hit_rows, key=lambda hit: hit.rrf_score, reverse=True)[:top_k]
