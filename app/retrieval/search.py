"""Soru metnini embed edip ChromaDB koleksiyonunda en yakın chunk'ları arar."""

from app.retrieval.embed import embed_text
from app.retrieval.index import get_collection


def search(
    query: str, top_k: int = 5, collection=None, content_types: list[str] | None = None
) -> list[dict]:
    """`content_types` verilirse yalnızca o türdeki chunk'lar aranır.

    Chunking aşamasında her chunk'a konan `content_type` etiketi burada
    işe yarıyor: tanım sorularında çözümlü örnek chunk'larını (`example`,
    `practice_problem`) dışarıda bırakmak için. Aksi halde cevaba örneğe
    özgü sayısal değerler ("1 kHz", "50 mH") karışıyor (gerçek kullanımda
    yakalandı — bkz. app/rag/generate.py::CONCEPT_CONTENT_TYPES).
    """
    collection = collection if collection is not None else get_collection()
    query_embedding = embed_text(query)
    where = {"content_type": {"$in": content_types}} if content_types else None
    result = collection.query(
        query_embeddings=[query_embedding], n_results=top_k, where=where
    )

    hits = []
    for i in range(len(result["ids"][0])):
        hits.append(
            {
                "chunk_id": result["ids"][0][i],
                "text": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            }
        )
    return hits
