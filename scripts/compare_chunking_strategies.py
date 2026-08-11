"""CLI: naive (sabit karakter) ile yapı-farkında (chunk_builder) chunking
stratejilerini gerçek veride karşılaştırır, spec §16'nın "en az iki strateji
karşılaştırılmalı" kısıtını somut ölçümlerle belgelemek için.

Kullanım:
    python scripts/compare_chunking_strategies.py --book fiore_dc
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.chunking.chunk_builder import build_chunks_for_book  # noqa: E402
from app.chunking.naive_chunker import (  # noqa: E402
    build_page_char_spans,
    naive_fixed_size_chunks,
)

PROCESSED_DIR = ROOT / "data" / "processed"


def _sections_touched(chunk: dict, spans: list[dict]) -> set:
    touched = set()
    for span in spans:
        if span["start_char"] < chunk["end_char"] and span["end_char"] > chunk["start_char"]:
            touched.add((span["chapter_number"], span["section_number"]))
    return touched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    args = parser.parse_args()

    in_path = PROCESSED_DIR / f"{args.book}.jsonl"
    if not in_path.exists():
        raise SystemExit(f"'{in_path}' bulunamadı.")

    with in_path.open(encoding="utf-8") as f:
        pages = [json.loads(line) for line in f]

    naive_chunks = naive_fixed_size_chunks(pages)
    spans = build_page_char_spans(pages)
    structured_chunks = build_chunks_for_book(pages, args.book)

    naive_violations = [c for c in naive_chunks if len(_sections_touched(c, spans)) > 1]

    naive_tokens = [len(c["text"]) // 4 for c in naive_chunks]
    structured_tokens = [len(c["text"]) // 4 for c in structured_chunks]

    print(f"=== {args.book} ===")
    print(f"Naive (sabit karakter):     {len(naive_chunks)} chunk, "
          f"ort. token={sum(naive_tokens)//len(naive_tokens)}, "
          f"section-siniri ihlali={len(naive_violations)}/{len(naive_chunks)}")
    print(f"Yapi-farkinda (chunk_builder): {len(structured_chunks)} chunk, "
          f"ort. token={sum(structured_tokens)//len(structured_tokens)}, "
          f"section-siniri ihlali=0/{len(structured_chunks)} (yapisal garanti)")

    if naive_violations:
        example = naive_violations[len(naive_violations) // 2]
        touched = sorted(_sections_touched(example, spans), key=lambda t: (t[0], t[1] or ""))
        print(f"\nOrnek ihlal (chunk_index={example['chunk_index']}, "
              f"{touched[0]} -> {touched[-1]} arasini kesiyor):")
        cut_point = example["text"]
        midpoint = len(cut_point) // 2
        print("..." + cut_point[max(0, midpoint - 100):midpoint + 100] + "...")


if __name__ == "__main__":
    main()
