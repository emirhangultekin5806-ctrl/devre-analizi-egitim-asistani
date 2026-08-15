"""RAG cevap kalitesi kontrolleri — `scripts/evaluate_rag.py` ve
`scripts/compare_rag_baseline.py` ORTAK kullanır.

Aynı vaka setini (`data/eval/rag_cases.json`) İKİ farklı üretim yoluna
(güncel numaralı-seçim mimarisi ve karşılaştırma için "naive" baseline)
karşı çalıştırmak gerektiği için buraya taşındı — mantık tek yerde,
iki script'te de birebir aynı ölçüt kullanılıyor.
"""

import re

_FRAC_RE = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")


def normalize_answer(text: str) -> str:
    """Cevabı LaTeX'ten arındırıp karşılaştırılabilir düz metne indirger.

    Cevaplar formülleri LaTeX ile yazıyor ($X_C = \\dfrac{-j}{2\\pi f C}$);
    vaka dosyasındaki beklentiler ise düz metin ("xc", "di/dt"). Bu fonksiyon
    ikisini ortak bir zemine getiriyor — böylece gösterim biçimi değişince
    tüm vakaları yeniden yazmak gerekmiyor.
    """
    text = _FRAC_RE.sub(r"\1/\2", text)  # \dfrac{a}{b} -> a/b
    text = _LATEX_CMD_RE.sub(" ", text)  # \pi, \cdot ... -> bosluk
    for ch in "${}_\\":
        text = text.replace(ch, "")
    return re.sub(r"\s+", " ", text).lower()


def is_refusal(answer: str, not_found_message: str) -> bool:
    return not_found_message.lower()[:35] in answer.lower()


def check_case(case: dict, answer: str, not_found_message: str) -> list[str]:
    """Vakayı değerlendirir, ihlal listesi döner (boşsa geçti)."""
    problems = []
    lowered = normalize_answer(answer)
    refused = is_refusal(answer, not_found_message)

    if case["expect"] == "refuse" and not refused:
        problems.append("reddetmesi gerekirken cevap verdi")
    if case["expect"] == "answer" and refused:
        problems.append("cevap vermesi gerekirken reddetti")

    if not refused:
        for term in case.get("must_contain", []):
            if normalize_answer(term) not in lowered:
                problems.append(f"'{term}' geçmiyor")
        for term in case.get("must_not_contain", []):
            if normalize_answer(term) in lowered:
                problems.append(f"'{term}' geçmemeliydi")
    return problems
