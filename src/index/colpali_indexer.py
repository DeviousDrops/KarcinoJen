"""ColPali visual embedding indexer for datasheet pages.

Renders PDF pages at 300 dpi, runs each through ColPali to produce
patch-level 128-d embeddings, and stores everything in a local directory
structure for MaxSim late-interaction retrieval.

Storage layout:
    data/colpali_index/{pdf_stem}/
        manifest.json          — page metadata
        embeddings/{page_id}.npy  — (num_patches, 128) float16
        images/{page_id}.png   — 300 dpi rendered page
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _ensure_colpali():
    """Import ColPali components; raises ImportError with guidance if missing."""
    try:
        from colpali_engine.models import ColPali, ColPaliProcessor
        return ColPali, ColPaliProcessor
    except ImportError:
        raise ImportError(
            "ColPali pipeline requires colpali-engine.\n"
            "Install with: pip install colpali-engine torch transformers"
        )


class ColPaliIndexer:
    """Builds and manages a local ColPali visual index for one datasheet."""

    def __init__(
        self,
        model_name: str = "vidore/colpali-v1.3-merged",
        index_root: str | Path = "data/colpali_index",
        device: str | None = None,
        batch_size: int = 2,
        render_dpi: int = 300,
    ):
        self.model_name = model_name
        self.index_root = Path(index_root)
        self._model = None
        self._processor = None
        self._device = device
        self._batch_size = max(1, int(batch_size))
        self._render_dpi = max(72, int(render_dpi))

    @staticmethod
    def _is_cuda_oom(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "out of memory" in msg and "cuda" in msg

    def _load_model(self):
        """Lazy-load ColPali model onto GPU/CPU."""
        if self._model is not None:
            return

        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        import torch
        ColPali, ColPaliProcessor = _ensure_colpali()

        device = self._device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info("Loading ColPali model %s on %s ...", self.model_name, device)
        t0 = time.perf_counter()

        self._model = ColPali.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            device_map=device,
        ).eval()
        self._processor = ColPaliProcessor.from_pretrained(self.model_name)

        logger.info("ColPali loaded in %.1fs", time.perf_counter() - t0)

    def index_datasheet(self, pdf_path: Path, *, force: bool = False) -> dict[str, Any]:
        """Index all pages of a PDF datasheet with ColPali embeddings.

        Returns the manifest dict with page metadata.
        """
        import torch
        from PIL import Image

        pdf_path = Path(pdf_path).resolve()
        stem = pdf_path.stem.lower()
        index_dir = self.index_root / stem
        manifest_path = index_dir / "manifest.json"

        # Skip re-indexing if manifest exists and not forced
        if manifest_path.exists() and not force:
            logger.info("Index already exists for %s, skipping (use force=True to rebuild)", stem)
            return json.loads(manifest_path.read_text(encoding="utf-8"))

        self._load_model()

        # Render pages
        try:
            import fitz  # type: ignore
        except ImportError:
            raise RuntimeError("PyMuPDF is required for PDF rendering")

        emb_dir = index_dir / "embeddings"
        img_dir = index_dir / "images"
        emb_dir.mkdir(parents=True, exist_ok=True)
        img_dir.mkdir(parents=True, exist_ok=True)

        pages_meta: list[dict[str, Any]] = []

        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)
            logger.info("Indexing %d pages from %s", total_pages, pdf_path.name)

            batch_size = self._batch_size
            page_idx = 0
            while page_idx < total_pages:
                batch_end = min(page_idx + batch_size, total_pages)
                batch_images = []
                batch_page_ids: list[str] = []
                batch_meta: list[dict[str, Any]] = []

                try:
                    for idx in range(page_idx, batch_end):
                        page = doc.load_page(idx)
                        page_number = idx + 1
                        page_id = f"{stem}_p{page_number}"

                        pix = page.get_pixmap(dpi=self._render_dpi)
                        img_path = img_dir / f"{page_id}.png"
                        pix.save(str(img_path))

                        img = Image.open(img_path).convert("RGB")
                        batch_images.append(img)
                        batch_page_ids.append(page_id)

                        text = page.get_text("text") or ""
                        batch_meta.append({
                            "page_id": page_id,
                            "source_file": pdf_path.name,
                            "page_number": page_number,
                            "image_path": str(img_path),
                            "embedding_path": str(emb_dir / f"{page_id}.npy"),
                            "text_preview": text[:500],
                            "text_length": len(text),
                        })

                    batch_input = self._processor.process_images(batch_images)
                    batch_input = {k: v.to(self._model.device) for k, v in batch_input.items()}

                    with torch.no_grad():
                        embeddings = self._model(**batch_input)

                    for i, page_id in enumerate(batch_page_ids):
                        page_emb = embeddings[i].cpu().float().numpy()  # (num_patches, 128)
                        np.save(emb_dir / f"{page_id}.npy", page_emb.astype(np.float16))

                    pages_meta.extend(batch_meta)

                    logger.info(
                        "  Indexed pages %d-%d / %d (batch=%d, dpi=%d)",
                        page_idx + 1,
                        batch_end,
                        total_pages,
                        batch_size,
                        self._render_dpi,
                    )
                    page_idx = batch_end

                except RuntimeError as exc:
                    if self._is_cuda_oom(exc):
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        if batch_size > 1:
                            new_batch = max(1, batch_size // 2)
                            logger.warning(
                                "CUDA OOM while indexing pages %d-%d. Reducing batch %d -> %d and retrying.",
                                page_idx + 1,
                                batch_end,
                                batch_size,
                                new_batch,
                            )
                            batch_size = new_batch
                            continue
                        raise RuntimeError(
                            "CUDA out of memory while indexing at batch_size=1. "
                            "Try closing other GPU workloads or switch retrieval backend."
                        ) from exc
                    raise
                finally:
                    for img in batch_images:
                        try:
                            img.close()
                        except Exception:
                            pass
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

        manifest = {
            "source_file": pdf_path.name,
            "stem": stem,
            "total_pages": total_pages,
            "model": self.model_name,
            "pages": pages_meta,
        }

        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("Index saved: %s (%d pages)", index_dir, total_pages)
        return manifest

    def load_index(self, pdf_stem: str) -> dict[str, Any] | None:
        """Load an existing index manifest."""
        manifest_path = self.index_root / pdf_stem.lower() / "manifest.json"
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a text query into ColPali token embeddings.

        Returns array of shape (num_tokens, 128).
        """
        import torch
        self._load_model()

        batch_query = self._processor.process_queries([query])
        batch_query = {k: v.to(self._model.device) for k, v in batch_query.items()}

        with torch.no_grad():
            query_emb = self._model(**batch_query)

        return query_emb[0].cpu().float().numpy()  # (num_tokens, 128)


def build_colpali_index(
    pdf_path: Path,
    *,
    model_name: str = "vidore/colpali-v1.3-merged",
    index_root: str | Path = "data/colpali_index",
    force: bool = False,
) -> dict[str, Any]:
    """Convenience function to build a ColPali index for a single datasheet."""
    indexer = ColPaliIndexer(model_name=model_name, index_root=index_root)
    return indexer.index_datasheet(pdf_path, force=force)
