"""Konu bazlı çoktan seçmeli quiz üretimi (spec: vizyon ekran 5).

`app/rag/generate.py` ile aynı temel ilkeyi izler: sorular modelin kendi
bilgisinden değil, KAYNAK CÜMLELERDEN üretilir. Aradaki fark, quiz'in
doğası gereği modelin metin üretmesi gerekmesi (soru + çeldiriciler);
bu yüzden burada "uydurma imkansız" değil, "uydurma sınırlandırılmış"
bir tasarım var:

- Aday cümleler RAG boru hattıyla aynı şekilde toplanır (arama → embedding
  ile sıralama), yani sorular gerçekten kitapta geçen içerikten çıkar.
- Model çıktısı JSON olarak istenir ve `_parse_quiz` ile katı biçimde
  doğrulanır; biçime uymayan/eksik sorular sessizce atılır.
- Doğru cevabın hangi kaynak cümleye dayandığı da istenir ve kullanıcıya
  gösterilir (öğrenci doğrulayabilsin).

Quiz "quality" kademesini kullanır (arka planda üretim, kullanıcı anlık
beklemiyor) — bkz. `app/rag/generate.py::TASK_TIERS`.
"""

import json
import re

from app.rag.generate import (
    CONCEPT_CONTENT_TYPES,
    MAX_CANDIDATE_SENTENCES,
    _call,
    _rank_candidates,
    _split_sentences,
    _translate_query_for_search,
    resolve_tier,
)
from app.retrieval.search import search

DEFAULT_QUESTION_COUNT = 5
_JSON_BLOCK_RE = re.compile(r"\[.*\]", re.DOTALL)

_QUIZ_SYSTEM_PROMPT = """Sen bir Devre Analizi öğretmenisin. Sana KAYNAK CÜMLELER verilecek; bunlara dayanarak çoktan seçmeli sınav soruları hazırlayacaksın.

KURALLAR:
- Sorular ve doğru cevaplar YALNIZCA kaynak cümlelerdeki bilgiye dayanmalı. Kaynakta olmayan bilgiyi soru yapma.
- Her sorunun 4 seçeneği (A, B, C, D) ve tek bir doğru cevabı olsun.
- Çeldiriciler makul olsun ama açıkça yanlış olsun.
- Sorular Türkçe olsun. Formül varsa LaTeX ile yaz ($X_C = \\dfrac{1}{2\\pi f C}$ gibi).
- Her soru için, doğru cevabın dayandığı kaynak cümleyi "kanit" alanına birebir yaz.

ÇIKTI BİÇİMİ — yalnızca şu JSON dizisini yaz, başka hiçbir şey yazma:
[
  {"soru": "...", "secenekler": {"A": "...", "B": "...", "C": "...", "D": "..."}, "dogru": "A", "kanit": "..."}
]"""


def _parse_quiz(raw: str, question_count: int) -> list[dict]:
    """Model çıktısını JSON olarak ayrıştırır; biçime uymayan soruları atar."""
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        options = item.get("secenekler")
        correct = item.get("dogru")
        if (
            not item.get("soru")
            or not isinstance(options, dict)
            or set(options) != {"A", "B", "C", "D"}
            or correct not in options
            or not all(str(v).strip() for v in options.values())
        ):
            continue
        valid.append(
            {
                "soru": str(item["soru"]).strip(),
                "secenekler": {k: str(v).strip() for k, v in options.items()},
                "dogru": correct,
                "kanit": str(item.get("kanit", "")).strip(),
            }
        )
    return valid[:question_count]


def generate_quiz(
    topic: str,
    question_count: int = DEFAULT_QUESTION_COUNT,
    top_k: int = 5,
    tier: str | None = None,
) -> dict:
    """Bir konu için çoktan seçmeli quiz üretir.

    Dönen: {"topic", "questions": [...], "sources": [...], "search_query"}
    `questions` boş dönebilir (model geçerli JSON üretemediyse) — çağıran
    taraf bunu kullanıcıya bildirmeli.
    """
    tier_config = resolve_tier(tier, task="quiz")
    search_query = _translate_query_for_search(topic, tier_config)
    hits = search(search_query, top_k=top_k, content_types=CONCEPT_CONTENT_TYPES)

    pool: list[str] = []
    for hit in hits:
        pool.extend(_split_sentences(hit["text"]))
    sentences = _rank_candidates(search_query, pool, MAX_CANDIDATE_SENTENCES)

    quoted = "\n".join(f"- {s}" for s in sentences)
    raw = _call(
        [
            {"role": "system", "content": _QUIZ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"KAYNAK CÜMLELER:\n{quoted}\n\n"
                    f"KONU: {topic}\n\n"
                    f"Bu kaynaklara dayanarak {question_count} soruluk quiz hazırla."
                ),
            },
        ],
        tier_config=tier_config,
    )

    return {
        "topic": topic,
        "search_query": search_query,
        "questions": _parse_quiz(raw, question_count),
        "sources": [
            {
                "chunk_id": hit["chunk_id"],
                "book_title": hit["metadata"].get("book_title"),
                "chapter_number": hit["metadata"].get("chapter_number"),
                "chapter_title": hit["metadata"].get("chapter_title"),
                "printed_page": hit["metadata"].get("printed_page"),
            }
            for hit in hits
        ],
    }
