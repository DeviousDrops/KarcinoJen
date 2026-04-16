"""Render datasheet PDF pages to images when optional dependencies are available."""

from __future__ import annotations

from pathlib import Path


def render_pdf_page(pdf_path: Path, page_number: int, out_dir: Path) -> Path | None:
    """Render a single 1-based page to PNG using PyMuPDF when available.

    Returns image path on success, or None when rendering backend is unavailable.
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{pdf_path.stem}_p{page_number}.png"

    with fitz.open(pdf_path) as document:
        index = page_number - 1
        if index < 0 or index >= len(document):
            raise ValueError(f"Page {page_number} out of range for {pdf_path}")
        page = document.load_page(index)
        pix = page.get_pixmap(dpi=150)
        pix.save(output_path)

    return output_path
