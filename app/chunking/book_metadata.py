"""Kitap-seviyesinde sabit metadata (spec §15'in chunk'tan chunk'a
değişmeyen alanları — book_title, authors, subject vb.).

Bu bilgiler her kitap için tek bir kez `docs/kaynaklar.md`'den elle
`data/metadata/books.json`'a aktarılır (uydurulmaz; bilinmeyen alanlar
`null` bırakılır, örn. Fiore DC'nin PDF'inde baskı/edition numarası
belirtilmediği için `edition: null`).
"""

import json
from pathlib import Path

_BOOKS_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "books.json"


def get_book_metadata(document_id: str) -> dict:
    with _BOOKS_JSON.open(encoding="utf-8") as f:
        books = json.load(f)
    if document_id not in books:
        raise KeyError(
            f"'{document_id}' icin data/metadata/books.json'da kayit yok."
        )
    return books[document_id]
