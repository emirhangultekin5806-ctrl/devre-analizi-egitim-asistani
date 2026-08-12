"""Soru metnini embed edip ChromaDB koleksiyonunda en yakın chunk'ları arar."""

from app.retrieval.embed import embed_text
from app.retrieval.index import get_collection


def search(query: str, top_k: int = 5, collection=None) -> list[dict]:
    collection = collection if collection is not None else get_collection()
    query_embedding = embed_text(query)
    result = collection.query(query_embeddings=[query_embedding], n_results=top_k)

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
