"""Bölüm/alt bölüm sınırı tespiti (spec §13, Adım 2 — kitap bazlı sezgisel).

Fiore'nin kitaplarında başlıklar kalın gösterim için iki kez art arda
render ediliyor:
    "1 1 Fundamentals"      <- çoğu bölüm: no + no + başlık, sonra başlık tekrarı
    "9 Inductors"           <- bazı bölümlerde: no + başlık (tek no), sonra başlık tekrarı
    "10" / "10 Magnetic..." <- bazı bölümlerde: no ayrı satırda, sonra "no + başlık", sonra başlık tekrarı
    "1.0 Chapter Learning Objectives" x2   <- alt bölüm: no + başlık, birebir tekrar

Tekrar eden satır her zaman birebir/tam eşleşmiyor:
    - Uzun başlıklarda ilk satır sarmalanabiliyor (Chapter 7:
      "7 7 Nodal & Mesh Analysis" + "Nodal & Mesh Analysis, Dependent Sources").
    - Bazen tekrar satırının ilk harfi PDF'in kendi metin katmanında kayıp
      çıkıyor (Chapter 8, AC kitabı: "8 8 Resonance" + "esonance" — büyük
      dekoratif "R" harfi ayrı bir nesne olduğu için metne tam yansımamış).
Bu yüzden birebir/startswith yerine **benzerlik oranına** dayalı toleranslı
bir eşleşme (`_similar`) kullanılıyor; başlık, daha tam olan tekrar
satırından alınıyor.

Kitabın sonundaki cevap anahtarı eki, her bölüm için "N Başlık" biçiminde
alt başlıklar içeriyor (örn. "9 Inductors") — bunların gerçek bölüm
geçişleriyle karıştırılmaması için yalnızca ardışık artan bölüm numaraları
(current + 1) kabul ediliyor.
"""

import re
from difflib import SequenceMatcher

_CHAPTER_RE = re.compile(r"^(\d+)\s+(?:\1\s+)?(\S.+)$")
_LONE_NUMBER_RE = re.compile(r"^(\d+)\s*$")
_SECTION_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")
_WORD_LIKE_RE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")

_SIMILARITY_THRESHOLD = 0.6
_MIN_LEN_FOR_FUZZY_MATCH = 6


def _looks_like_title(text: str) -> bool:
    """En az 4 harflik kesintisiz bir "kelime" içeriyor mu?

    Devre denklemleri ("8 V = 5ΩI 1+8Ω(I1+3A)" gibi) sembol/rakam ağırlıklı
    olduğu için bu testi geçemez; gerçek başlıklar (tek kelimelik "Resonance"
    dahil) hep en az bir gerçek kelime içerir.
    """
    return bool(_WORD_LIKE_RE.search(text))


def _similar(a: str, b: str) -> bool:
    """İki satırın "aynı başlığın tekrarı" olma ihtimalini kabaca ölçer.

    Birebir eşitlik yerine kullanılıyor çünkü tekrar satırı bazen sarmalanmış
    (daha uzun) ya da PDF'in metin katmanında bir harf eksik çıkabiliyor.

    İki ek güvenlik filtresi var (sahte bölüm eşleşmesini önlemek için):
    1. Kısa metinlerde (örn. bir formülün parçası olan "8 V c" gibi) benzerlik
       oranı tesadüfen yüksek çıkabildiği için, belirli bir uzunluğun
       altındaki metinler yalnızca birebir eşleşirse kabul edilir.
    2. Ardışık cebirsel çözüm adımları da (örn. "8 V = 5ΩI 1+8ΩI 2" ->
       "8 V = 5ΩI 1+8Ω(I1+3A)") tesadüfen yüksek oranla benzeyebiliyor; bu
       yüzden her iki metnin de gerçek bir "kelime" içermesi şart koşuluyor.
    """
    if not a or not b:
        return False
    if not (_looks_like_title(a) and _looks_like_title(b)):
        return False
    if len(a) < _MIN_LEN_FOR_FUZZY_MATCH or len(b) < _MIN_LEN_FOR_FUZZY_MATCH:
        return a == b
    return SequenceMatcher(None, a, b).ratio() >= _SIMILARITY_THRESHOLD


_SPLASH_RE = re.compile(r"^c\s*h\s*a\s*p\s*t\s*e\s*r\Z", re.IGNORECASE)
_SPLASH_NUMBER_RE = re.compile(r"^(\d+)\Z")
_VERSO_RE = re.compile(r"^Chapter (\d+)\Z")
_RECTO_RE = re.compile(r"^(\d+)\.(\d+)\Z")
_LONE_DIGIT_RE = re.compile(r"^\d+\Z")

_BOOTSTRAP_LOOKAHEAD = 40  # sayfa; gerçek bir bölüm başlangıcının kaç sayfa
# içinde çalışan-başlık pekiştirmesiyle teyit edilmesi beklendiği — kitabın
# yapısal bir garantisi değil, gözlemlenen en geniş boşluğun (1 sayfa) çok
# üzerinde seçilmiş güvenli bir sabit.


def _sadiku_reinforcement(pages: list[dict], start: int, end: int, chapter_number: int) -> str | None:
    """`pages[start:end]` içinde `chapter_number`'ı teyit eden bir çalışan
    başlık (verso ya da recto) arar, bulursa bölüm başlığını döndürür.

    Sadiku'nun "chapter splash" sayfası tek başına güvenilir değil — kitabın
    "Guided Tour" tanıtım bölümü, gerçek bir bölüm splash sayfasını ekran
    görüntüsü gibi birebir içeriyor (bkz. modül docstring'i). Gerçek bir
    bölüm başlangıcının hemen ardından mutlaka aynı bölüm numarasıyla
    çalışan başlıklar gelir; sahte/yeniden-üretilmiş splash'ların ardından
    gelmez — bu farkı ayırt etmek için kullanılıyor.
    """
    for page in pages[start:end]:
        lines = [line.strip() for line in page["raw_text"].splitlines() if line.strip()]
        for i in range(len(lines) - 2):
            a, b, c = lines[i], lines[i + 1], lines[i + 2]
            verso_match = _LONE_DIGIT_RE.match(a) and _VERSO_RE.match(b)
            if verso_match and int(_VERSO_RE.match(b).group(1)) == chapter_number and _looks_like_title(c):
                return c
            recto_match = _RECTO_RE.match(a) and _LONE_DIGIT_RE.match(c)
            if recto_match and int(_RECTO_RE.match(a).group(1)) == chapter_number and _looks_like_title(b):
                return b
    return None


def detect_structure_sadiku(pages: list[dict]) -> list[dict]:
    """Sadiku (Fundamentals of Electric Circuits) için chapter/section alanlarını doldurur.

    Fiore'den tamamen farklı bir yerleşim: her bölüm "c h a p t e r\\n<no>"
    biçiminde harf-aralıklı bir "splash" sayfasıyla açılıyor, gövde
    sayfalarında ise iki farklı çalışan başlık biçimi var:
        verso: "<basılı sayfa no>\\nChapter <N>\\n<bölüm başlığı>"
        recto: "<N>.<M>\\n<alt bölüm başlığı>\\n<basılı sayfa no>"
    Fiore'nin bold-render tekrarı burada yok; bunun yerine splash sayfası
    TEK BAŞINA güvenilmiyor (kitabın "Guided Tour" tanıtım bölümü gerçek bir
    splash sayfasını birebir içeriyor) — her aday, ardından gelen sayfalarda
    aynı bölüm numarasıyla bir çalışan-başlık pekiştirmesi bulunarak teyit
    ediliyor (`_sadiku_reinforcement`). İlk bölüm numarası kitaba göre
    değişiyor (`sadiku_1` 1'den, `sadiku_2` 13'ten başlıyor), o yüzden sabit
    bir başlangıç varsayımı yok; teyit edilen ilk bölümden sonra yalnızca
    ardışık artan numaralar kabul ediliyor.
    """
    candidates = []
    for page in pages:
        lines = [line.strip() for line in page["raw_text"].splitlines() if line.strip()]
        for i in range(len(lines) - 1):
            if _SPLASH_RE.match(lines[i]):
                m = _SPLASH_NUMBER_RE.match(lines[i + 1])
                if m:
                    candidates.append((page["page_number"], int(m.group(1))))

    confirmed = {}  # page_number -> (chapter_number, chapter_title)
    current = None
    for idx, n in candidates:
        if current is not None and n != current + 1:
            continue
        title = _sadiku_reinforcement(pages, idx, idx + _BOOTSTRAP_LOOKAHEAD, n)
        if title is None:
            continue
        confirmed[idx] = (n, title)
        current = n

    chapter_number = chapter_title = section_number = section_title = None
    for page in pages:
        if page["page_number"] in confirmed:
            chapter_number, chapter_title = confirmed[page["page_number"]]
            section_number = section_title = None
        elif chapter_number is not None:
            lines = [line.strip() for line in page["raw_text"].splitlines() if line.strip()]
            for i in range(len(lines) - 2):
                a, b, c = lines[i], lines[i + 1], lines[i + 2]
                if (
                    _LONE_DIGIT_RE.match(a)
                    and _VERSO_RE.match(b)
                    and int(_VERSO_RE.match(b).group(1)) == chapter_number
                    and _looks_like_title(c)
                ):
                    chapter_title = c
                m = _RECTO_RE.match(a)
                if (
                    m
                    and int(m.group(1)) == chapter_number
                    and _LONE_DIGIT_RE.match(c)
                    and _looks_like_title(b)
                ):
                    section_number = f"{m.group(1)}.{m.group(2)}"
                    section_title = b

        page["chapter_number"] = chapter_number
        page["chapter_title"] = chapter_title
        page["section_number"] = section_number
        page["section_title"] = section_title

    return pages


def detect_structure_fiore(pages: list[dict]) -> list[dict]:
    """Fiore kitapları için chapter/section alanlarını doldurur (yerinde günceller)."""
    chapter_number = None
    chapter_title = None
    section_number = None
    section_title = None

    for page in pages:
        lines = [line.strip() for line in page["raw_text"].splitlines()]

        for i in range(len(lines) - 1):
            line, next_line = lines[i], lines[i + 1]
            expected_next = (chapter_number or 0) + 1

            chapter_match = _CHAPTER_RE.match(line)
            if (
                chapter_match
                and int(chapter_match.group(1)) == expected_next
                and _similar(chapter_match.group(2).strip(), next_line)
            ):
                chapter_number = int(chapter_match.group(1))
                # Tekrar satırı, orijinalinden daha uzun/tamsa onu tercih et.
                chapter_title = max(chapter_match.group(2).strip(), next_line, key=len)
                section_number = None
                section_title = None
                continue

            # "10\n10 Magnetic Circuits and Transformers\nMagnetic Circuits..." gibi
            # numaranın kendi satırında yalnız durduğu durum.
            lone_match = _LONE_NUMBER_RE.match(line)
            if lone_match and int(lone_match.group(1)) == expected_next and i + 2 < len(lines):
                after = lines[i + 2]
                second_line_match = re.match(
                    rf"^{lone_match.group(1)}\s+(\S.+)$", next_line
                )
                if second_line_match and _similar(second_line_match.group(1).strip(), after):
                    chapter_number = int(lone_match.group(1))
                    chapter_title = max(second_line_match.group(1).strip(), after, key=len)
                    section_number = None
                    section_title = None
                    continue

            section_match = _SECTION_RE.match(line)
            if (
                section_match
                and _similar(line, next_line)
                and section_match.group(1).split(".")[0] == str(chapter_number)
            ):
                next_match = _SECTION_RE.match(next_line) or section_match
                section_number = next_match.group(1)
                section_title = next_match.group(2).strip()

        page["chapter_number"] = chapter_number
        page["chapter_title"] = chapter_title
        page["section_number"] = section_number
        page["section_title"] = section_title

    return pages
