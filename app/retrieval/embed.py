"""Ollama üzerinden embedding üretimi (yalnızca local LLM, harici API yok).

Model olarak `bge-m3` seçildi: çok dilli (Türkçe soru — İngilizce kaynak
kitap eşleşmesi gerekiyor, bkz. docs/vision.md). `ollama pull bge-m3` ile
bu makinede zaten indirildi (1.2 GB, 1024 boyutlu vektör üretiyor).

`/api/embed` (toplu, `input` bir liste alabiliyor) kullanılıyor —
`/api/embeddings` (tekil, `prompt`) yaklaşık 12 kat daha yavaş çıktı
(gerçek veride ölçüldü: 2.8s/chunk vs 0.31s/chunk), 4 kitabın tamamını
(2173 chunk) index'lemek tekil istekle ~1.7 saat, toplu istekle ~11 dakika
sürüyor.
"""

import requests

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBEDDING_MODEL = "bge-m3"
BATCH_SIZE = 100


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = requests.post(
            OLLAMA_EMBED_URL, json={"model": EMBEDDING_MODEL, "input": batch}, timeout=300
        )
        response.raise_for_status()
        embeddings.extend(response.json()["embeddings"])
    return embeddings
