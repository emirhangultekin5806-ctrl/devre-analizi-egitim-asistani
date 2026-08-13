"""Ders kitabındaki alıştırmalardan (soru, bilinen cevap) çiftleri çıkarır.

Amaç: öz-doğrulama döngüsü için bir **cevap anahtarı** oluşturmak. Sistem
bir devreyi kendi çözer, sonra buradaki `expected_answer` ile karşılaştırır;
tutuyorsa topoloji okuması doğrulanmış sayılır.

**Cevap sızıntısına karşı yapısal koruma.** Sadiku'da alıştırmanın cevabı
sorunun hemen altındadır ("... Answer: 7.36 mA."). Chunk olduğu gibi
çözücüye/modele verilirse cevabı görür ve "çözmüş" gibi görünür — bu,
doğrulamanın tamamını anlamsızlaştırır. Bu yüzden:

- `Problem.text` cevabın ÖNCESİNDEKİ metinle sınırlıdır; "Answer:" ve
  sonrası asla içine girmez.
- `Problem.expected_answer` ayrı bir alandır ve yalnızca karşılaştırma
  aşamasında kullanılmalıdır.
- `extract_problems` her kaydı üretirken bu ayrımı test edilebilir biçimde
  garanti eder (bkz. tests/test_problems.py).

**Bilinen sınırlama.** Alıştırmaların çoğunda devre bir ŞEKİLDE'dir; metin
yalnızca eleman değerlerini içerir, topolojiyi içermez ("Figure 2.36 ...
5 Ω 4 Ω 6 Ω"). Yani bu kayıtlar tek başına çözülebilir değildir; görsel
katman gelene kadar değerleri **cevap anahtarı** olarak kullanılır.
`figure_refs` alanı, hangi şeklin okunması gerektiğini işaret eder.
"""

import re
from dataclasses import dataclass, field

_PROBLEM_HEADING_RE = re.compile(r"Practice Problem\s+(\d+\.\d+)", re.IGNORECASE)
_ANSWER_RE = re.compile(r"\bAnswers?\s*:", re.IGNORECASE)
_FIGURE_REF_RE = re.compile(r"\bFig(?:ure)?\.?\s*(\d+\.\d+)", re.IGNORECASE)
# Sayı + birim: "7.36 mA", "6 Ω", "12 V", "1.78 A", "3.709 kW"
# Birimlerde BÜYÜK/KÜÇÜK HARF ÖNEMLİ: "S" siemens, "s" saniye; "V" volt.
# re.IGNORECASE kullanılırsa "16.667 s" siemens sanılıyor (gerçek veride
# yakalandı). Bu yüzden birim kısmı bilerek harf duyarlı bırakıldı.
_VALUE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(k|M|G|m|µ|μ|n|p)?\s*(Ω|ohm|V|A|W|F|H|Hz|S|s|VA|VAR|J|C)\b"
)
_SI_PREFIX = {"k": 1e3, "M": 1e6, "G": 1e9, "m": 1e-3, "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12}


@dataclass(frozen=True)
class Problem:
    """Bir alıştırma: soru metni ve BİLİNEN cevabı (ayrı alanlarda)."""

    problem_id: str
    document_id: str
    chunk_id: str
    text: str
    expected_answer: str
    values: tuple[tuple[float, str], ...] = field(default_factory=tuple)
    figure_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Sızıntı koruması: soru metni cevabı içeremez.
        if _ANSWER_RE.search(self.text):
            raise ValueError(
                f"{self.problem_id}: soru metni cevap içeriyor — çözüm öncesi cevap sızıntısı"
            )


def parse_answer_values(answer: str) -> tuple[tuple[float, str], ...]:
    """Cevap metnindeki sayısal değerleri (SI ölçeklenmiş) ve birimlerini çıkarır.

    "Answer: 7.36 mA." -> ((0.00736, 'A'),)
    "Answer: (a) 15 V, 20 V" -> ((15.0, 'V'), (20.0, 'V'))

    Ölçekleme yapılıyor ki karşılaştırma birimden bağımsız olsun (7.36 mA
    ile 0.00736 A aynı sayılsın).
    """
    values = []
    for number, prefix, unit in _VALUE_RE.findall(answer):
        scale = _SI_PREFIX.get(prefix, 1.0) if prefix else 1.0
        unit_normalized = "Ω" if unit.lower() in {"ohm", "ω"} else unit
        values.append((float(number) * scale, unit_normalized))
    return tuple(values)


def extract_problems(chunks: list[dict]) -> list[Problem]:
    """Chunk listesinden (soru, cevap) çiftlerini çıkarır.

    Yalnızca hem "Practice Problem N.M" başlığı hem "Answer:" içeren
    chunk'lar alınır — cevabı olmayan bir alıştırma doğrulama için
    kullanılamaz, sessizce atlanır.
    """
    problems: list[Problem] = []
    for chunk in chunks:
        text = chunk.get("text", "")
        heading = _PROBLEM_HEADING_RE.search(text)
        answer_match = _ANSWER_RE.search(text)
        if not heading or not answer_match:
            continue
        if answer_match.start() <= heading.end():
            continue  # cevap başlıktan önce: başka bir alıştırmanın cevabı

        question = text[heading.end() : answer_match.start()].strip()
        if not question:
            continue

        # Cevap TEK SATIRDIR. Gerçek veride kalıp şu: "Answer: 7.36 mA.\n"
        # ardından bambaşka içerik geliyor (bir önceki örneğin çözüm
        # adımları, şekil etiketleri...). Satır sonuna kadar almak yerine
        # daha gevşek bir sınır kullanmak, cevaba ait olmayan sayıları
        # `values` içine sokuyordu (gerçek veride yakalandı).
        # "Answer:" hemen ardından satır sonu geliyorsa cevap alt satırdadır.
        tail = text[answer_match.end() :].lstrip("\n\r\t ")
        answer = tail.split("\n", 1)[0].strip()

        problems.append(
            Problem(
                problem_id=f"{chunk['document_id']} Practice Problem {heading.group(1)}",
                document_id=chunk["document_id"],
                chunk_id=chunk["chunk_id"],
                text=question,
                expected_answer=answer,
                values=parse_answer_values(answer),
                figure_refs=tuple(dict.fromkeys(_FIGURE_REF_RE.findall(text))),
            )
        )
    return problems
