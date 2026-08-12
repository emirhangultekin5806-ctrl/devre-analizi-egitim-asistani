"""Chunk'ları embed edip çalışan bir Chroma sunucusuna (HTTP) yazar.

`PersistentClient` (gömülü/dosya modu) bu makinede gerçek indeksleme
yükünde (Ollama'dan embedding beklerken dakikalarca açık kalan process +
chromadb'nin arka plan compaction thread'i) güvenilmez çıktı: index
dosyalarını bozup sonraki HER okumayı "Error loading hnsw index" ile
kırdı (3/3 gerçek çalıştırmada tekrarlandı, `chroma vacuum` da
düzeltmedi). Client-server moduna geçildi — dosyaya YALNIZCA sunucu
process'i erişiyor, o hiç yeniden başlatılmadığı sürece bu bozulma sınıfı
oluşamaz.

Sunucu, Ollama gibi arka planda çalışan ayrı bir servis olarak
başlatılmalı:
    chroma run --path data/indexes/chroma --port 8123

Chroma'nın metadata alanları `None` ya da liste kabul etmiyor (yalnızca
str/int/float/bool) — bu yüzden `authors` gibi liste alanları düz metne
çevrilir, hâlâ `None` olan alanlar (difficulty, keywords, vb. — Adım 2'de
bilinçli olarak boş bırakılmıştı) atlanır, sorgu tarafında o alanın
eksikliği "henüz sınıflandırılmadı" anlamına gelir.
"""

import chromadb

from app.retrieval.embed import embed_texts

CHROMA_HOST = "localhost"
CHROMA_PORT = 8123
COLLECTION_NAME = "devre_analizi_chunks"


def get_collection(
    collection_name: str = COLLECTION_NAME, host: str = CHROMA_HOST, port: int = CHROMA_PORT
):
    client = chromadb.HttpClient(host=host, port=port)
    # bge-m3 (cogu embedding modeli gibi) cosine similarity icin egitildi;
    # Chroma'nin varsayilani (L2/Oklid) normalize edilmemis 1024 boyutlu
    # vektorlerde yorumlanmasi zor buyuk degerler veriyordu (500-800 araligi).
    return client.get_or_create_collection(
        collection_name, metadata={"hnsw:space": "cosine"}
    )


def _sanitize_metadata(chunk: dict) -> dict:
    metadata = {}
    for key, value in chunk.items():
        if key in ("chunk_id", "text"):
            continue
        if value is None:
            continue
        if isinstance(value, list):
            metadata[key] = ", ".join(value)
        else:
            metadata[key] = value
    return metadata


def index_chunks(chunks: list[dict], collection=None) -> None:
    collection = collection if collection is not None else get_collection()
    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    embeddings = embed_texts(documents)
    metadatas = [_sanitize_metadata(c) for c in chunks]

    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
