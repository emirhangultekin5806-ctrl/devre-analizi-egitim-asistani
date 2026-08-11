"""Paragraf-seviyesinde content_type tespiti (Adım 2, spec §15).

Gerçek veride doğrulanan sinyaller:
- "Example N.M" ile başlayan blok -> example (Fiore + Sadiku'da var)
- "Practice Problem N.M" ile başlayan blok -> practice_problem (yalnızca Sadiku'da var)
- "N.0 Chapter Learning Objectives" ile başlayan blok -> learning_objectives (yalnızca Fiore'de var)
- "N.M Summary" (Fiore) ya da tek başına "Summary" satırı (Sadiku) ile başlayan
  blok -> chapter_summary
- Diğerleri -> concept (varsayılan)

Önemli bulgu 1: bu başlık satırları çoğunlukla paragrafın ("\\n\\n" ile ayrılmış
blok) İÇİNDE, önceki cümlenin hemen ardına yapışık çıkıyor (aralarında boş
satır yok) — örn. "...odometer'a güvenemeyiz.\\nExample 1.2\\nPerform the
following...". Gerçek veri taramasında paragraf-başı anchor eşleşmesi
fiore_dc'de 98 Example'ın yalnızca 17'sini, sadiku_1'de 183'ünün 0'ını
yakaladı. Bu yüzden `split_embedded_headings()` önce satır satır taranıp bu
başlıkların önüne paragraf sınırı ekliyor; asıl sınıflandırma bu bölünmüş
paragraflar üzerinde çalışıyor.

Önemli bulgu 2: `chapter_summary` tespiti bilinçli olarak `section_title ==
"Summary"` yerine bu paragraf-seviyesi başlık deseni kullanıyor.
`app/ingestion/structure_detect.py`'nin Sadiku detektörü bazı bölümlerde
sonraki section sınırını bulamıyor ve o "Summary" section'ına asıl özetten
sonraki tüm sayfaları (Review Questions, Problems, hatta 136 sayfaya kadar)
yanlışlıkla dahil ediyor (gerçek veride doğrulandı — bu, chunking'in değil,
önceden commit'lenmiş ingestion aşamasının bilinen bir kusuru, ayrı bir turda
düzeltilecek). Paragraf-seviyesi başlık deseni bu kusurun etkisini
sınırlıyor: yalnızca gerçekten "Summary" satırıyla başlayan paragraf
chapter_summary olur, section'ın geri kalanı (yanlışlıkla aynı section'a
yapışmış problem sayfaları) `concept`'e düşer — yanlış ama en azından
"chapter_summary" gibi yanıltıcı şekilde etiketlenmez.

`^Summary\\Z` (tam satır) kullanılıyor, `^Summary\\b` değil — Sadiku'da
"Summary of Bode straight-line magnitude..." gibi bölüm-içi alt başlıklar da
"Summary" ile başlıyor ama bunlar chapter summary değil.
"""

import re

_EXAMPLE_RE = re.compile(r"^Example \d+\.\d+\b")
_PRACTICE_PROBLEM_RE = re.compile(r"^Practice Problem \d+\.\d+\b")
_LEARNING_OBJECTIVES_RE = re.compile(r"^\d+\.0 Chapter Learning Objectives\b")
_SUMMARY_RE = re.compile(r"^(?:\d+\.\d+ )?Summary\Z")

_BLOCK_HEADING_PATTERNS = (_EXAMPLE_RE, _PRACTICE_PROBLEM_RE, _LEARNING_OBJECTIVES_RE, _SUMMARY_RE)


def split_embedded_headings(paragraphs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Bir başlık satırı, içinde bulunduğu paragrafın ortasında geçiyorsa
    paragrafı oradan ikiye böler (başlık yeni paragrafın ilk satırı olur).
    Sayfa numarası (page) her iki parça için de korunur.
    """
    result: list[tuple[str, int]] = []
    for text, page in paragraphs:
        lines = text.split("\n")
        current: list[str] = []
        for line in lines:
            if current and any(p.match(line.strip()) for p in _BLOCK_HEADING_PATTERNS):
                result.append(("\n".join(current), page))
                current = [line]
            else:
                current.append(line)
        if current:
            result.append(("\n".join(current), page))
    return result


def classify_paragraph(text: str) -> str:
    first_line = text.lstrip().split("\n", 1)[0].strip()
    if _EXAMPLE_RE.match(first_line):
        return "example"
    if _PRACTICE_PROBLEM_RE.match(first_line):
        return "practice_problem"
    if _LEARNING_OBJECTIVES_RE.match(first_line):
        return "learning_objectives"
    if _SUMMARY_RE.match(first_line):
        return "chapter_summary"
    return "concept"


def group_by_content_type(
    paragraphs: list[tuple[str, int]],
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Ardışık aynı-content_type paragrafları tek blokta toplar; her blok
    kendi content_type'ıyla ayrı ayrı paketlenecek (bkz. chunk_builder.py) —
    böylece bir Example bloğu bitişikteki concept metniyle aynı chunk'a
    karışmaz.
    """
    blocks: list[tuple[str, list[tuple[str, int]]]] = []
    current_type: str | None = None
    current_paras: list[tuple[str, int]] = []

    for text, page in paragraphs:
        ctype = classify_paragraph(text)
        if ctype != current_type:
            if current_paras:
                blocks.append((current_type, current_paras))
            current_type = ctype
            current_paras = []
        current_paras.append((text, page))

    if current_paras:
        blocks.append((current_type, current_paras))

    return blocks
