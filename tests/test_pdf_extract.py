from pathlib import Path

from app.ingestion.pdf_extract import extract_pages

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC = ROOT / "data" / "raw" / "open" / "Fiore_DC_Electrical_Circuit_Analysis.pdf"


def test_extract_pages_returns_readable_text():
    pages = extract_pages(FIORE_DC, "fiore_dc")

    assert len(pages) == 374

    # İlk 20 sayfa arasında en az birkaçı okunabilir metin içermeli
    # (kapak/boş sayfalar olabileceği için tamamı değil).
    readable = [p for p in pages[:20] if p["char_count"] > 100]
    assert len(readable) > 5

    for page in pages:
        assert page["document_id"] == "fiore_dc"
        assert page["extraction_method"] == "pymupdf"
        assert isinstance(page["needs_review"], bool)
