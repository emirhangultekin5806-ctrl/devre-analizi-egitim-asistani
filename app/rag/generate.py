"""Retrieval + local LLM (Ollama, qwen3:4b) ile kaynaklı cevap üretimi.

qwen3:4b bu projede gerçekçi bir RAG senaryosuyla doğrulandı (bkz.
docs/vision.md): kaynakta olan bir soruda doğru cevabı verdi, kaynakta
OLMAYAN bir soruda uydurmadan "bilmiyorum" dedi (halüsinasyon riski
testini geçti). Aynı sistem promptu deseni burada üretim koduna taşındı.

Bilinen sınırlama — "thinking" modu kapatılamıyor: `think: false` API
parametresi ve `/no_think` prompt yönergesi ikisi de denendi, ikisi de bu
Ollama/model kombinasyonunda etkisiz çıktı (VLM'lerde daha önce görülen
aynı sorun, bkz. docs/vlm-karsilastirma-sonuclari.md). Model her yanıttan
önce `<think>...</think>` bloğunda uzun bir iç akıl yürütme üretiyor —
gerçek veride 5 chunk'lık bağlamla 200-320 saniye sürdü. `_strip_thinking()`
bu bloğu son kullanıcıya gösterilecek metinden ayıklıyor; süre kısaltılamıyor,
yalnızca çıktı temizleniyor.
"""

import re

import requests

from app.retrieval.search import search

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
GENERATION_MODEL = "qwen3:4b"
GENERATE_TIMEOUT_SECONDS = 400

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_SYSTEM_PROMPT = (
    "Sen bir Devre Analizi ders asistanısın. Yalnızca aşağıda verilen "
    "kaynak metinleri kullanarak Türkçe cevap ver. Kaynaklarda cevap yoksa "
    "kesinlikle uydurma, tam olarak şunu de: "
    "'Seçilen ders kitaplarında bu bilgiye ulaşamadım.' "
    "Cevabının sonunda hangi kaynak(lar)dan yararlandığını (kitap, bölüm) belirt."
)


def _format_context(hits: list[dict]) -> str:
    parts = []
    for i, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        label = (
            f"[Kaynak {i}: {meta.get('book_title')}, "
            f"Bölüm {meta.get('chapter_number')} - {meta.get('chapter_title')}]"
        )
        parts.append(f"{label}\n{hit['text']}")
    return "\n\n".join(parts)


def _strip_thinking(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


def answer_question(question: str, top_k: int = 5) -> dict:
    hits = search(question, top_k=top_k)
    context = _format_context(hits)
    prompt = f"{_SYSTEM_PROMPT}\n\nKAYNAKLAR:\n{context}\n\nSORU: {question}\n\nCEVAP:"

    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={"model": GENERATION_MODEL, "prompt": prompt, "stream": False},
        timeout=GENERATE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    answer_text = _strip_thinking(response.json()["response"])

    return {
        "question": question,
        "answer": answer_text,
        "sources": [
            {
                "chunk_id": hit["chunk_id"],
                "book_title": hit["metadata"].get("book_title"),
                "chapter_number": hit["metadata"].get("chapter_number"),
                "chapter_title": hit["metadata"].get("chapter_title"),
                "section_number": hit["metadata"].get("section_number"),
            }
            for hit in hits
        ],
    }
