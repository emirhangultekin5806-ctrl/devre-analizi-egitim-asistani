"""CLI: data/chunks/<document_id>.jsonl dosyalarını okuyup embed edip
çalışan bir Chroma sunucusuna yazar.

Kullanım:
    chroma run --path data/indexes/chroma --port 8123   # ayrı terminalde, arka planda
    python scripts/build_index.py --book fiore_dc
    python scripts/build_index.py --all

ÖNEMLİ (gerçek veride doğrulandı): ChromaDB'nin gömülü/dosya modu
(`PersistentClient`) bu makinede güvenilmez çıktı — gerçek indeksleme
yükünde (Ollama'dan embedding beklerken dakikalarca açık kalan process)
index dosyalarını bozdu, sonraki her okuma "Error loading hnsw index" ile
kırıldı (3/3 gerçek çalıştırmada tekrarlandı, `chroma vacuum` da
düzeltmedi). Bunun yerine Chroma artık Ollama gibi ayrı bir arka plan
servisi olarak (`chroma run`) çalıştırılıyor, `app/retrieval/index.py`
`HttpClient` ile ona bağlanıyor — dosyaya yalnızca sunucu process'i
erişiyor, bu bozulma sınıfı böylece oluşamıyor (bkz. index.py docstring'i).

Bozulursa kurtarma: sunucuyu durdurup `data/indexes/chroma` klasörünü
silip yeniden başlatmak yeterli — chunk verisi (`data/chunks/`) kaynak,
index tamamen yeniden üretilebilir (~10 dakika, 4 kitap ~2170 chunk).

Önkoşul: scripts/chunk_books.py ilgili kitap(lar) için zaten çalıştırılmış
olmalı, Ollama çalışıyor olmalı (`ollama pull bge-m3` yapılmış), Chroma
sunucusu ayrı bir terminalde çalışıyor olmalı.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.retrieval.index import get_collection, index_chunks  # noqa: E402

CHUNKS_DIR = ROOT / "data" / "chunks"
ALL_BOOKS = ["fiore_dc", "fiore_ac", "sadiku_full"]


def _load_chunks(book: str) -> list[dict]:
    in_path = CHUNKS_DIR / f"{book}.jsonl"
    if not in_path.exists():
        raise SystemExit(f"'{in_path}' bulunamadı. Önce: python scripts/chunk_books.py --book {book}")
    with in_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", help="Tek kitap (yalnızca tek kitap index'lenecekse)")
    group.add_argument("--all", action="store_true", help="Tüm kitapları tek process içinde index'ler")
    args = parser.parse_args()

    books = ALL_BOOKS if args.all else [args.book]
    collection = get_collection()

    for book in books:
        chunks = _load_chunks(book)
        index_chunks(chunks, collection=collection)
        print(f"Index'lendi: {len(chunks)} chunk ({book}) -- toplam koleksiyon: {collection.count()}")


if __name__ == "__main__":
    main()
