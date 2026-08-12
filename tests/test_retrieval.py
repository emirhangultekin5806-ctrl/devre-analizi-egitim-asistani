import chromadb
import pytest
import requests

from app.retrieval.index import (
    CHROMA_HOST,
    CHROMA_PORT,
    _sanitize_metadata,
    get_collection,
    index_chunks,
)
from app.retrieval.search import search


def _ollama_embeddings_available() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return any(m.startswith("bge-m3") for m in models)
    except requests.RequestException:
        return False


def _chroma_server_available() -> bool:
    try:
        r = requests.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


skip_no_ollama = pytest.mark.skipif(
    not _ollama_embeddings_available(),
    reason="Ollama calismiyor ya da bge-m3 modeli indirilmemis",
)
skip_no_chroma_server = pytest.mark.skipif(
    not _chroma_server_available(),
    reason="Chroma sunucusu calismiyor (bkz: chroma run --path data/indexes/chroma --port 8123)",
)


def test_sanitize_metadata_drops_none_values():
    chunk = {"chunk_id": "x", "text": "body", "difficulty": None, "chapter_number": 1}
    result = _sanitize_metadata(chunk)
    assert "difficulty" not in result
    assert "chunk_id" not in result
    assert "text" not in result
    assert result["chapter_number"] == 1


def test_sanitize_metadata_joins_list_fields():
    chunk = {"chunk_id": "x", "text": "body", "authors": ["A. Author", "B. Author"]}
    result = _sanitize_metadata(chunk)
    assert result["authors"] == "A. Author, B. Author"


@skip_no_ollama
@skip_no_chroma_server
def test_index_and_search_real_ollama_returns_relevant_chunk():
    collection = get_collection(collection_name="test_collection_retrieval")
    try:
        chunks = [
            {
                "chunk_id": "a1",
                "text": "Kirchhoff's Current Law states that the sum of currents entering a node equals the sum leaving it.",
                "chapter_number": 4,
                "content_type": "concept",
            },
            {
                "chunk_id": "a2",
                "text": "A capacitor stores energy in an electric field between two conductive plates.",
                "chapter_number": 8,
                "content_type": "concept",
            },
        ]
        index_chunks(chunks, collection=collection)

        results = search("akım yasası nedir?", top_k=1, collection=collection)
        assert results[0]["chunk_id"] == "a1"
    finally:
        chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT).delete_collection(
            "test_collection_retrieval"
        )
