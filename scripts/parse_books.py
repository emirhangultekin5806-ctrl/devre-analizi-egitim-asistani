"""CLI: bir kitabı sayfa bazlı çıkarıp data/processed/<document_id>.jsonl yazar.

Kullanım:
    python scripts/parse_books.py --book fiore_dc
    python scripts/parse_books.py --book sadiku_1 --path "C:/.../Devre analizi-1.pdf"
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.pdf_extract import extract_pages  # noqa: E402
from app.ingestion.structure_detect import detect_structure_fiore  # noqa: E402

KNOWN_BOOKS = {
    "fiore_dc": ROOT / "data" / "raw" / "open" / "Fiore_DC_Electrical_Circuit_Analysis.pdf",
    "fiore_ac": ROOT / "data" / "raw" / "open" / "Fiore_AC_Electrical_Circuit_Analysis.pdf",
}

# document_id -> yapı tespit fonksiyonu (kitap bazlı; henüz yalnızca Fiore için var)
STRUCTURE_DETECTORS = {
    "fiore_dc": detect_structure_fiore,
    "fiore_ac": detect_structure_fiore,
}

OUTPUT_DIR = ROOT / "data" / "processed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, help="document_id (örn. fiore_dc)")
    parser.add_argument("--path", help="PDF yolu (KNOWN_BOOKS'ta yoksa zorunlu)")
    args = parser.parse_args()

    pdf_path = Path(args.path) if args.path else KNOWN_BOOKS.get(args.book)
    if pdf_path is None:
        raise SystemExit(f"'{args.book}' için --path belirtilmeli.")
    if not pdf_path.exists():
        raise SystemExit(f"Dosya bulunamadı: {pdf_path}")

    pages = extract_pages(pdf_path, args.book)

    detector = STRUCTURE_DETECTORS.get(args.book)
    if detector:
        pages = detector(pages)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{args.book}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for record in pages:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    needs_review = sum(1 for p in pages if p["needs_review"])
    with_chapter = sum(1 for p in pages if p["chapter_number"] is not None)
    print(f"Yazıldı: {out_path} ({len(pages)} sayfa, needs_review={needs_review})")
    if detector:
        print(f"chapter_number dolu: {with_chapter}/{len(pages)} sayfa")


if __name__ == "__main__":
    main()
