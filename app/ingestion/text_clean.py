"""Ham metin temizliği (spec §13, Adım 3-4 — kitap bazlı sezgisel).

Fiore PDF'lerinden çıkarılan `raw_text` şu gürültü kalıplarını içeriyor:
    1. Tam sayfa "Notes" ayraç sayfaları — sabit 5 satırlık desen
       ("Notes" x2, dekoratif satır x2, sayfa no).
    2. Sayfa numarası satırı (`page_number + 1`) — sayfanın herhangi bir
       yerinde olabilir, her zaman son satır değil.
    3. TOC nokta-lider satırları ("." tekrarları).
    4. `structure_detect.py`'nin de bildiği kalın-başlık render tekrarı:
       ardışık birebir aynı satırlar.

`clean_text()` bu gürültüyü kaldırır ama `raw_text`'i asla değiştirmez —
çağıran taraf ikisini de saklar. Yalnızca Fiore DC/AC için doğrulandı;
Sadiku'ya doğrudan uygulanmamalı — farklı bir gürültü profili var (bkz.
`clean_text_sadiku` docstring'i), örneğin devre şeması etiketlerindeki
meşru ardışık tekrarları bozar.

Sadiku'da `page_number + 1 == basılı sayfa no` varsayımı geçerli değil
(ön-madde kayması var, `page.get_label()` de kullanılamıyor) — bunun yerine
`compute_page_offset()` çalışan başlıklardaki basılı sayfa no'larından
çoğunluk oyuyla sabit bir ofset çıkarır, `clean_text_sadiku()` de bu ofseti
kullanır. Ofset güvenilir değilse (yetersiz/belirsiz sinyal) ya da o sayfa
için beklenen basılı no ön-madde bölgesindeyse (`<= 0`), yanlış tahminle
içerik bozmaktansa satır silinmeden yalnızca boşluk normalizasyonu yapılır.
"""

import re
from collections import Counter

_MULTI_BLANK_RE = re.compile(r"\n{3,}")

_SADIKU_VERSO_RE = re.compile(r"^Chapter (\d+)\Z")
_SADIKU_RECTO_RE = re.compile(r"^(\d+)\.(\d+)\Z")
_SADIKU_LONE_DIGIT_RE = re.compile(r"^\d+\Z")
_SADIKU_WORD_LIKE_RE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")

_OFFSET_MIN_SUPPORT = 10
_OFFSET_DOMINANCE_RATIO = 2.0


def clean_text(raw_text: str, page_number: int) -> str:
    lines = raw_text.split("\n")
    stripped = [line.strip() for line in lines]

    content = [s for s in stripped if s != ""]
    if (
        len(content) == 5
        and content[0] == "Notes"
        and content[1] == "Notes"
        and content[2] == content[3]
        and content[4] == str(page_number + 1)
    ):
        return ""

    # Ardışık birebir aynı satırları tek satıra indirger. Orijinal satır
    # sırası üzerinde çalışır (gürültü satırları silinmeden önce) çünkü
    # "ardışık" tanımı raw_text'teki bitişikliğe dayanıyor; önce silme
    # yapılırsa aralarında gürültü satırı olan iki farklı satır yanlışlıkla
    # bitişik hale gelip birleştirilebilir.
    deduped = []
    for original_line, s in zip(lines, stripped):
        if s != "" and deduped and deduped[-1][1] == s:
            continue
        deduped.append((original_line, s))

    kept = []
    for original_line, s in deduped:
        if s == ".":
            continue
        if s.isdigit() and int(s) == page_number + 1:
            continue
        kept.append(original_line)

    text = "\n".join(kept)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def compute_page_offset(pages: list[dict]) -> int | None:
    """Sayfa numarası ofsetini (page_number - basılı sayfa no) çoğunluk oyuyla hesaplar.

    Ham verso/recto taraması (structure_detect.py'deki bölüm-tutarlılık
    guard'ları OLMADAN — burada amaç tek bir sayı, tüm kitap için sabit bir
    ofset) TOC ve sayısal tablo gibi gürültü kaynaklarından yanlış eşleşmeler
    üretebilir, ama gerçek veride doğru ofset lehine olan eşleşme sayısı
    ezici çoğunlukta (Sadiku vol1/vol2'de %68-90 arası doğrulandı) — bu
    yüzden basit bir mod (en sık değer) yeterli ve güvenilir.

    Yeterli ya da baskın bir sinyal yoksa `None` döner (ofset kullanılmadan
    `clean_text_sadiku` sayfa no satırını silmeden geçer).
    """
    offsets = Counter()
    for page in pages:
        lines = [line.strip() for line in page["raw_text"].splitlines() if line.strip()]
        for i in range(len(lines) - 2):
            a, b, c = lines[i], lines[i + 1], lines[i + 2]
            if (
                _SADIKU_LONE_DIGIT_RE.match(a)
                and _SADIKU_VERSO_RE.match(b)
                and _SADIKU_WORD_LIKE_RE.search(c)
            ):
                offsets[page["page_number"] - int(a)] += 1
            if (
                _SADIKU_RECTO_RE.match(a)
                and _SADIKU_LONE_DIGIT_RE.match(c)
                and _SADIKU_WORD_LIKE_RE.search(b)
            ):
                offsets[page["page_number"] - int(c)] += 1

    if not offsets:
        return None
    winner, count = offsets.most_common(1)[0]
    total = sum(offsets.values())
    rest = total - count
    if count < _OFFSET_MIN_SUPPORT or count < _OFFSET_DOMINANCE_RATIO * max(rest, 1):
        return None
    return winner


def clean_text_sadiku(raw_text: str, page_number: int, offset: int | None) -> str:
    """Sadiku için sayfa no footer'ını kaldırır; başka gürültü türüne dokunmaz.

    Fiore'nin ardışık-aynı-satır birleştirme kuralı buraya taşınmadı —
    gerçek veri taramasında bunun devre şeması etiketlerindeki meşru
    tekrarları (`+−`, `2 A` gibi) bozacağı doğrulandı. TOC nokta-lider
    temizliği de yok — Sadiku'nun TOC'unda nokta-lider zaten bulunmuyor.

    Ön-madde (roma rakamlı önsöz/TOC), Index (`I-N`) ve Ek (`A-N`, `C.4`)
    sayfalarının footer'ları bilerek temizlenmiyor: `offset` bu bölgelerde
    geçerli olmadığından (`expected_printed <= 0`), yanlış tahminle içerik
    bozmaktansa dokunmadan bırakılıyor.
    """
    if offset is not None:
        expected_printed = page_number - offset
        if expected_printed > 0:
            lines = raw_text.split("\n")
            kept = [
                line
                for line in lines
                if line.strip() != str(expected_printed)
            ]
            raw_text = "\n".join(kept)

    text = _MULTI_BLANK_RE.sub("\n\n", raw_text)
    return text.strip()
