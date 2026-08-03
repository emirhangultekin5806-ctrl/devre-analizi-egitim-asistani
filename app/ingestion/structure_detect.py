"""Bölüm/alt bölüm sınırı tespiti (spec §13, Adım 2 — kitap bazlı sezgisel).

Fiore'nin kitaplarında başlıklar kalın gösterim için iki kez art arda
render ediliyor:
    "1 1 Fundamentals"      <- çoğu bölüm: no + no + başlık, sonra başlık tekrarı
    "9 Inductors"           <- bazı bölümlerde: no + başlık (tek no), sonra başlık tekrarı
    "10" / "10 Magnetic..." <- bazı bölümlerde: no ayrı satırda, sonra "no + başlık", sonra başlık tekrarı
    "1.0 Chapter Learning Objectives" x2   <- alt bölüm: no + başlık, birebir tekrar

Uzun başlıklarda ilk satır sarmalanabiliyor (örn. Chapter 7:
"7 7 Nodal & Mesh Analysis" + "Nodal & Mesh Analysis, Dependent Sources"),
bu yüzden birebir eşitlik yerine "startswith" toleranslı eşleşme kullanılıyor
ve başlık, daha tam olan tekrar satırından alınıyor.

Kitabın sonundaki cevap anahtarı eki, her bölüm için "N Başlık" biçiminde
alt başlıklar içeriyor (örn. "9 Inductors") — bunların gerçek bölüm
geçişleriyle karıştırılmaması için yalnızca ardışık artan bölüm numaraları
(current + 1) kabul ediliyor.
"""

import re

_CHAPTER_RE = re.compile(r"^(\d+)\s+(?:\1\s+)?(\S.+)$")
_LONE_NUMBER_RE = re.compile(r"^(\d+)\s*$")
_SECTION_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")


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
                and next_line.startswith(chapter_match.group(2).strip())
            ):
                chapter_number = int(chapter_match.group(1))
                chapter_title = next_line.strip()
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
                if second_line_match and after.startswith(second_line_match.group(1).strip()):
                    chapter_number = int(lone_match.group(1))
                    chapter_title = after.strip()
                    section_number = None
                    section_title = None
                    continue

            section_match = _SECTION_RE.match(line)
            if (
                section_match
                and next_line.startswith(line)
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
