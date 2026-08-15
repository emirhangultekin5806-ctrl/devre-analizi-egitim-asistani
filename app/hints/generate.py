"""Serbest cevaplı soru + kademeli ipucu modu (spec: vizyon ekran 6).

`app/quiz/generate.py` ile aynı temel desen: sorular modelin kendi
bilgisinden değil KAYNAK CÜMLELERDEN üretilir, model çıktısı JSON olarak
istenip katı biçimde doğrulanır. Farkı: quiz çoktan seçmeli, bu mod
SERBEST METİN — öğrenci kendi cümleleriyle cevap yazar, sistem bunu
doğru/kısmen doğru/yanlış/yetersiz diye değerlendirir ve tam doğru
değilse cevabı DOĞRUDAN VERMEDEN kademeli (1-3) ipucu üretir.

Üç ayrı adım, üç ayrı fonksiyon (`generate_question`, `evaluate_answer`,
`generate_hint`) — aralarındaki durum (soru, kaynak cümleler, hangi ipucu
seviyesine gelindiği) ÇAĞIRAN TARAFTA (arayüzde) tutulur, burada değil;
böylece her adım bağımsız test edilebilir ve arayüz akışı (öğrenci bir
sonraki ipucu seviyesine ne zaman geçer) burada varsayılmaz.

İpucu modu "fast" kademesini kullanır (öğrenci canlı bekliyor, hız kaliteden
öncelikli) — bkz. `app/rag/generate.py::TASK_TIERS["hint"]`.
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

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

VERDICTS = {"dogru", "kismen_dogru", "yanlis", "yetersiz"}
MAX_HINT_LEVEL = 3
_FALLBACK_EVALUATION = {
    "degerlendirme": "yetersiz",
    "aciklama": "Değerlendirme üretilemedi, lütfen tekrar deneyin.",
}

_QUESTION_SYSTEM_PROMPT = """Sen bir Devre Analizi öğretmenisin. Sana KAYNAK CÜMLELER verilecek; bunlara dayanarak öğrencinin SERBEST METİNLE (çoktan seçmeli DEĞİL) cevaplayacağı TEK bir soru hazırlayacaksın.

KURALLAR:
- Soru YALNIZCA kaynak cümlelerdeki bilgiye dayanmalı, kaynakta olmayan bir şey sorma.
- Sorunun net, tek bir doğru cevap kümesi olmalı (yoruma açık olmasın).
- Türkçe yaz.

ÇIKTI BİÇİMİ — yalnızca şu JSON nesnesini yaz, başka hiçbir şey yazma:
{"soru": "..."}"""

_EVALUATE_SYSTEM_PROMPT = """Sen bir Devre Analizi öğretmenisin. Öğrenciye bir soru soruldu; sana KAYNAK CÜMLELER, SORU ve ÖĞRENCİNİN CEVABI verilecek. Cevabı değerlendireceksin.

DEĞERLENDİRME ÖLÇÜTLERİ (yalnızca kaynak cümlelerdeki bilgiye göre):
- "dogru": cevap eksiksiz ve doğru.
- "kismen_dogru": cevap doğru yönde ama eksik ya da küçük bir hata var.
- "yanlis": cevap kaynaktaki bilgiyle açıkça çelişiyor.
- "yetersiz": cevap konuyla ilgisiz, boş, ya da "bilmiyorum" gibi.

KRİTİK KURAL: değerlendirme "dogru" DEĞİLSE, "aciklama" alanında doğru
cevabı YA DA doğru cevabın büyük kısmını SÖYLEME — yalnızca neyin eksik
ya da yanlış OLDUĞUNU işaret et, ne olması GEREKTİĞİNİ değil. Kısa ol
(1-2 cümle). Türkçe yaz.

ÇIKTI BİÇİMİ — yalnızca şu JSON nesnesini yaz, başka hiçbir şey yazma:
{"degerlendirme": "dogru"|"kismen_dogru"|"yanlis"|"yetersiz", "aciklama": "..."}"""

_HINT_SYSTEM_PROMPT_TEMPLATE = """Sen bir Devre Analizi öğretmenisin. Öğrenci bir soruya tam doğru cevap veremedi. Ona {level}. SEVİYE ipucu vereceksin (toplam 3 kademeli seviye var).

KURALLAR (kesinlikle uy):
- Cevabı ASLA doğrudan söyleme — sonucu, sayıyı ya da nihai formülü verme.
- SEVİYE 1: yalnızca hangi KAVRAMA/KURALA bakması gerektiğini hatırlat; yönlendirici bir soru sor.
- SEVİYE 2: ilgili TANIMI ya da FORMÜLÜ ver, ama öğrencinin bunu soruya nasıl uygulayacağını kendisine bırak.
- SEVİYE 3: öğrencinin cevabındaki eksik/hatalı noktayı açıkça işaret et, doğru cevaba iyice yaklaştır — ama SONUCUN KENDİSİNİ söyleme.
- Yalnızca verilen kaynak cümlelerdeki bilgiyi kullan.
- Kısa ol (1-3 cümle), Türkçe yaz.

ÇIKTI: yalnızca ipucu metnini yaz — başına/sonuna etiket, JSON ya da açıklama ekleme."""


def _parse_question(raw: str) -> str | None:
    """Model çıktısını JSON olarak ayrıştırır; biçime uymuyorsa None döner."""
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    question = data.get("soru") if isinstance(data, dict) else None
    return str(question).strip() if question and str(question).strip() else None


def _parse_evaluation(raw: str) -> dict:
    """Model çıktısını JSON olarak ayrıştırır; biçime uymuyorsa güvenli bir
    geri düşüşe ("yetersiz" + tekrar dene mesajı) döner — asla `KeyError`
    ya da geçersiz bir `degerlendirme` değeriyle çağırana sessizce yanlış
    bilgi sızdırmaz."""
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return dict(_FALLBACK_EVALUATION)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return dict(_FALLBACK_EVALUATION)
    if not isinstance(data, dict):
        return dict(_FALLBACK_EVALUATION)
    verdict = data.get("degerlendirme")
    if verdict not in VERDICTS:
        return dict(_FALLBACK_EVALUATION)
    return {"degerlendirme": verdict, "aciklama": str(data.get("aciklama", "")).strip()}


def _source_summaries(hits: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": hit["chunk_id"],
            "book_title": hit["metadata"].get("book_title"),
            "chapter_number": hit["metadata"].get("chapter_number"),
            "chapter_title": hit["metadata"].get("chapter_title"),
            "printed_page": hit["metadata"].get("printed_page"),
        }
        for hit in hits
    ]


def generate_question(topic: str, top_k: int = 5, tier: str | None = None) -> dict:
    """Bir konu için SERBEST CEVAPLI tek soru üretir.

    Dönen: {"topic", "search_query", "question", "source_sentences", "sources"}.
    `question` None dönebilir (model geçerli JSON üretemediyse) — çağıran
    taraf bunu kullanıcıya bildirmeli. `source_sentences`, `evaluate_answer`
    ve `generate_hint`'e AYNEN geçirilmeli (soru hangi kanıta dayandıysa
    değerlendirme de o kanıta göre yapılmalı).
    """
    tier_config = resolve_tier(tier, task="hint")
    search_query = _translate_query_for_search(topic, tier_config)
    hits = search(search_query, top_k=top_k, content_types=CONCEPT_CONTENT_TYPES)

    pool: list[str] = []
    for hit in hits:
        pool.extend(_split_sentences(hit["text"]))
    sentences = _rank_candidates(search_query, pool, MAX_CANDIDATE_SENTENCES)

    quoted = "\n".join(f"- {s}" for s in sentences)
    raw = _call(
        [
            {"role": "system", "content": _QUESTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"KAYNAK CÜMLELER:\n{quoted}\n\nKONU: {topic}"},
        ],
        tier_config=tier_config,
    )

    return {
        "topic": topic,
        "search_query": search_query,
        "question": _parse_question(raw),
        "source_sentences": sentences,
        "sources": _source_summaries(hits),
    }


def evaluate_answer(
    question: str, source_sentences: list[str], student_answer: str, tier: str | None = None
) -> dict:
    """Öğrencinin serbest metin cevabını değerlendirir.

    Dönen: {"degerlendirme": "dogru"|"kismen_dogru"|"yanlis"|"yetersiz", "aciklama": "..."}.
    Model geçerli JSON üretemezse `_FALLBACK_EVALUATION` döner (asla hatalı
    bir "dogru" iddia etmez — belirsizlikte en az bilgi veren tarafa düşer).
    """
    tier_config = resolve_tier(tier, task="hint")
    quoted = "\n".join(f"- {s}" for s in source_sentences)
    raw = _call(
        [
            {"role": "system", "content": _EVALUATE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"KAYNAK CÜMLELER:\n{quoted}\n\nSORU: {question}\n\n"
                    f"ÖĞRENCİNİN CEVABI: {student_answer}"
                ),
            },
        ],
        tier_config=tier_config,
    )
    return _parse_evaluation(raw)


def generate_hint(
    question: str,
    source_sentences: list[str],
    student_answer: str,
    hint_level: int,
    tier: str | None = None,
) -> str:
    """Kademeli ipucu (1-3. seviye) — cevabı DOĞRUDAN VERMEZ.

    `hint_level` çağıran tarafta (arayüzde) tutulur ve öğrenci "bir ipucu
    daha" istedikçe artırılır — bu fonksiyon kendi başına bir oturum/durum
    tutmaz, her çağrı bağımsızdır.
    """
    if not 1 <= hint_level <= MAX_HINT_LEVEL:
        raise ValueError(f"hint_level 1-{MAX_HINT_LEVEL} arasında olmalı, verilen: {hint_level}")
    tier_config = resolve_tier(tier, task="hint")
    quoted = "\n".join(f"- {s}" for s in source_sentences)
    system_prompt = _HINT_SYSTEM_PROMPT_TEMPLATE.format(level=hint_level)
    return _call(
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"KAYNAK CÜMLELER:\n{quoted}\n\nSORU: {question}\n\n"
                    f"ÖĞRENCİNİN CEVABI: {student_answer}"
                ),
            },
        ],
        tier_config=tier_config,
    ).strip()
