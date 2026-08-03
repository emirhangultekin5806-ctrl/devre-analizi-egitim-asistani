"""PDF'lerden sayfa bazlı ham metin çıkarımı (spec §13, Adım 1).

Bölüm/alt bölüm tespiti ve temizleme sonraki adımlarda eklenecek;
burada yalnızca ham metin + temel sayfa bilgisi çıkarılır.
"""

from pathlib import Path

import fitz  # PyMuPDF

NEEDS_REVIEW_MIN_CHARS = 30


def extract_pages(pdf_path: Path, document_id: str) -> list[dict]:
    """PDF'in her sayfası için bir kayıt döndürür."""
    doc = fitz.open(pdf_path)
    pages = []
    for index, page in enumerate(doc):
        raw_text = page.get_text()
        char_count = len(raw_text.strip())
        pages.append(
            {
                "document_id": document_id,
                "source_file": str(pdf_path),
                "page_number": index,
                "page_label": page.get_label() or None,
                "raw_text": raw_text,
                "char_count": char_count,
                "extraction_method": "pymupdf",
                "chapter_number": None,
                "chapter_title": None,
                "section_number": None,
                "section_title": None,
                "needs_review": char_count < NEEDS_REVIEW_MIN_CHARS,
            }
        )
    doc.close()
    return pages
