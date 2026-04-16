"""Compare lexical vs Chroma retrieval on a query set."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extractor.model_config import RetrievalConfig, load_runtime_config
from src.retrieval.chroma_retriever import retrieve_top_pages

CONFIG_PATH = ROOT / "configs" / "model_config.json"
DEFAULT_QUERY_FILE = ROOT / "data" / "mcu-bench" / "queries.jsonl"
DEFAULT_DATASHEET = ROOT / "data" / "datasheets" / "stm32f401-ds.pdf"
DEFAULT_OUTDIR = ROOT / "runs" / "retrieval_compare"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_queries(query_file: Path) -> list[dict[str, Any]]:
    if not query_file.exists():
        return [
            {
                "id": "q01",
                "query": "Find RCC AHB1ENR GPIOAEN bit",
                "expected_page_id": None,
            },
            {
                "id": "q02",
                "query": "Find GPIOA MODER reset value",
                "expected_page_id": None,
            },
            {
                "id": "q03",
                "query": "Find USART2 CR1 UE bit position",
                "expected_page_id": None,
            },
        ]

    rows: list[dict[str, Any]] = []
    with query_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            query_text = str(entry.get("query", "")).strip()
            if not query_text:
                continue
            rows.append(
                {
                    "id": str(entry.get("id", f"q{len(rows) + 1:03d}")),
                    "query": query_text,
                    "expected_page_id": entry.get("expected_page_id"),
                }
            )

    if not rows:
        raise RuntimeError(f"No valid query rows in file: {query_file}")
    return rows


def _score_metrics(results: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    hit_flags: list[int] = []
    reciprocal_ranks: list[float] = []

    for row in results:
        expected_page_id = row.get("expected_page_id")
        retrieved_ids: list[str] = row["retrieved_page_ids"]

        if not expected_page_id:
            continue

        if expected_page_id in retrieved_ids[:top_k]:
            hit_flags.append(1)
        else:
            hit_flags.append(0)

        rr = 0.0
        for index, page_id in enumerate(retrieved_ids, start=1):
            if page_id == expected_page_id:
                rr = 1.0 / index
                break
        reciprocal_ranks.append(rr)

    judged = len(hit_flags)
    if judged == 0:
        return {
            "judged_queries": 0,
            f"recall@{top_k}": None,
            "mrr": None,
        }

    return {
        "judged_queries": judged,
        f"recall@{top_k}": sum(hit_flags) / judged,
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
    }


def _run_backend(
    *,
    queries: list[dict[str, Any]],
    datasheet_path: Path,
    retrieval_cfg: RetrievalConfig,
    backend: str,
) -> dict[str, Any]:
    cfg = replace(retrieval_cfg, backend=backend)

    rows: list[dict[str, Any]] = []
    latencies_ms: list[float] = []

    for query in queries:
        start = time.perf_counter()
        top_pages = retrieve_top_pages(
            query=query["query"],
            datasheet_path=datasheet_path,
            retrieval_cfg=cfg,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies_ms.append(elapsed_ms)

        rows.append(
            {
                "id": query["id"],
                "query": query["query"],
                "expected_page_id": query.get("expected_page_id"),
                "retrieved_page_ids": [str(page.get("page_id")) for page in top_pages],
                "latency_ms": round(elapsed_ms, 3),
            }
        )

    summary = {
        "backend": backend,
        "query_count": len(rows),
        "latency_ms_mean": round(statistics.mean(latencies_ms), 3),
        "latency_ms_median": round(statistics.median(latencies_ms), 3),
        "latency_ms_p95": round(sorted(latencies_ms)[max(0, int(0.95 * len(latencies_ms)) - 1)], 3),
    }
    summary.update(_score_metrics(rows, cfg.top_k))

    return {
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare lexical and Chroma retrieval backends")
    parser.add_argument("--datasheet", type=Path, default=DEFAULT_DATASHEET)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    if not args.datasheet.exists():
        raise FileNotFoundError(f"Datasheet not found: {args.datasheet}")

    runtime_cfg = load_runtime_config(CONFIG_PATH)
    queries = _load_queries(args.queries)

    print(f"Datasheet: {args.datasheet}")
    print(f"Queries: {args.queries if args.queries.exists() else 'fallback built-in set'}")
    print(f"Top-k: {runtime_cfg.retrieval.top_k}")

    lexical = _run_backend(
        queries=queries,
        datasheet_path=args.datasheet,
        retrieval_cfg=runtime_cfg.retrieval,
        backend="lexical",
    )
    chroma = _run_backend(
        queries=queries,
        datasheet_path=args.datasheet,
        retrieval_cfg=runtime_cfg.retrieval,
        backend="chroma",
    )

    report = {
        "created_utc": _utc_stamp(),
        "datasheet": str(args.datasheet),
        "queries_file": str(args.queries),
        "top_k": runtime_cfg.retrieval.top_k,
        "results": {
            "lexical": lexical,
            "chroma": chroma,
        },
    }

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_path = args.outdir / f"compare_{_utc_stamp()}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nSummary")
    for backend_name in ["lexical", "chroma"]:
        summary = report["results"][backend_name]["summary"]
        recall_key = f"recall@{runtime_cfg.retrieval.top_k}"
        print(
            f"- {backend_name:7s} | mean={summary['latency_ms_mean']:8.3f} ms"
            f" | median={summary['latency_ms_median']:8.3f} ms"
            f" | p95={summary['latency_ms_p95']:8.3f} ms"
            f" | {recall_key}={summary[recall_key]} | mrr={summary['mrr']}"
        )

    print(f"\nReport written: {out_path}")


if __name__ == "__main__":
    main()
