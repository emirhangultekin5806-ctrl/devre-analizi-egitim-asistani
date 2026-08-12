"""CLI: bir soruyu retrieval + local LLM (qwen3:4b) ile cevaplar.

Kullanım:
    python scripts/ask.py "Kirchhoff akım yasası nedir?"

Önkoşul: Ollama çalışıyor olmalı, Chroma sunucusu çalışıyor olmalı
(`chroma run --path data/indexes/chroma --port 8123`), index kurulmuş
olmalı (`scripts/build_index.py --all`).

Not: bir cevap yaklaşık 25-50 saniye sürüyor (iki LLM çağrısı: cümle
seçimi + çeviri, bkz. app/rag/generate.py).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.rag.generate import answer_question  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    print("Düşünüyor (3-5 dakika sürebilir)...")
    result = answer_question(args.question, top_k=args.top_k)

    print()
    print("CEVAP:")
    print(result["answer"])
    print()
    print("KAYNAKLAR:")
    for source in result["sources"]:
        print(
            f"  - {source['book_title']}, Bölüm {source['chapter_number']}"
            f" ({source['chapter_title']})"
        )


if __name__ == "__main__":
    main()
