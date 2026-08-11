"""CLI: data/processed/<document_id>.jsonl'i okuyup chunk'lara boler,
data/chunks/<document_id>.jsonl olarak yazar.

Kullanim:
    python scripts/chunk_books.py --book fiore_dc

Onkosul: scripts/parse_books.py bu kitap icin zaten calistirilmis olmali
(data/processed/<document_id>.jsonl mevcut olmali).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.chunking.chunk_builder import build_chunks_for_book  # noqa: E402

PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "data" / "chunks"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, help="document_id (orn. fiore_dc)")
    args = parser.parse_args()

    in_path = PROCESSED_DIR / f"{args.book}.jsonl"
    if not in_path.exists():
        raise SystemExit(
            f"'{in_path}' bulunamadi. Once: python scripts/parse_books.py --book {args.book}"
        )

    with in_path.open(encoding="utf-8") as f:
        pages = [json.loads(line) for line in f]

    chunks = build_chunks_for_book(pages, args.book)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{args.book}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    token_counts = [len(c["text"]) // 4 for c in chunks]
    avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 0
    print(f"Yazildi: {out_path} ({len(chunks)} chunk)")
    print(f"Ortalama token tahmini: {avg_tokens:.0f}")


if __name__ == "__main__":
    main()
