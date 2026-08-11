"""Section'ları token bütçesine göre chunk'lara paketler ve spec §15'in
21 alanlık metadata şemasını doldurur.

Bu turda (Adım 1) tüm chunk'lar tek bir hedef aralık kullanır — spec'in
"tanım/kavram" hedefine en yakın genel amaçlı değer (250-650 token) —
çünkü content_type sınıflandırması henüz yok (Adım 2), her chunk şimdilik
`"concept"` olarak etiketleniyor. `difficulty`, `learning_objective`,
`prerequisites`, `keywords` alanları da aynı nedenle bilinçli olarak
`None` bırakılıyor; sonraki adımlarda dolduruluyor.

`printed_page` iki farklı stratejiyle türetilir (bkz. app/ingestion/text_clean.py):
Fiore'de `page_number + 1` sabit; Sadiku'da sabit ofset yok, bu yüzden
`compute_page_offset()` ile kitap genelinde çoğunluk oyuyla bir ofset
hesaplanır. Ofset güvenilir çıkmazsa (yetersiz sinyal) `printed_page`
uydurulmaz, `None` bırakılır — `chunk_id` o durumda `page_number`'a düşer.
"""

from app.chunking.book_metadata import get_book_metadata
from app.chunking.segment import build_segments
from app.chunking.tokenizer import estimate_tokens
from app.ingestion.text_clean import compute_page_offset

TARGET_TOKENS = 500
MAX_TOKENS = 650
MIN_TAIL_TOKENS = 80

# Sadiku'da sabit +1 ofseti geçerli değil (bkz. text_clean.py docstring'i);
# parse_books.py'deki SADIKU_BOOKS ile aynı gerekçe/kapsam.
SADIKU_BOOKS = {"sadiku_1", "sadiku_2"}


def _compute_printed_page(document_id: str, page_number: int, sadiku_offset: int | None) -> int | None:
    if document_id in SADIKU_BOOKS:
        if sadiku_offset is None:
            return None
        return page_number - sadiku_offset
    return page_number + 1


def _pack_paragraphs(paragraphs: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """[(text, page_number), ...] -> [(birlesik_metin, baslangic_sayfa, bitis_sayfa), ...]

    Hedefe (TARGET_TOKENS) ulaşınca yeni chunk açılır; sert tavanı
    (MAX_TOKENS) aşacak bir paragraf eklenmeden önce mevcut chunk
    kapatılır. Son kalan parça çok küçükse (MIN_TAIL_TOKENS altı),
    yetim mini-chunk bırakmamak için bir önceki chunk'a eklenir.
    """
    chunks: list[tuple[str, int, int]] = []
    buf: list[str] = []
    buf_tokens = 0
    start_page = None
    end_page = None

    for text, page in paragraphs:
        t = estimate_tokens(text)
        if buf and buf_tokens + t > MAX_TOKENS:
            chunks.append(("\n\n".join(buf), start_page, end_page))
            buf, buf_tokens, start_page = [], 0, None
        if start_page is None:
            start_page = page
        buf.append(text)
        buf_tokens += t
        end_page = page
        if buf_tokens >= TARGET_TOKENS:
            chunks.append(("\n\n".join(buf), start_page, end_page))
            buf, buf_tokens, start_page = [], 0, None

    if buf:
        if chunks and buf_tokens < MIN_TAIL_TOKENS:
            prev_text, prev_start, _ = chunks[-1]
            chunks[-1] = (prev_text + "\n\n" + "\n\n".join(buf), prev_start, end_page)
        else:
            chunks.append(("\n\n".join(buf), start_page, end_page))

    return chunks


def _build_chunk_id(document_id: str, chapter_number: int, section_number: str | None,
                     printed_page: int, seq: int) -> str:
    section_part = (section_number or "0").replace(".", "")
    return f"{document_id}_ch{chapter_number}_s{section_part}_p{printed_page}_c{seq:02d}"


def build_chunks_for_book(pages: list[dict], document_id: str) -> list[dict]:
    book_meta = get_book_metadata(document_id)
    sections = build_segments(pages)
    sadiku_offset = compute_page_offset(pages) if document_id in SADIKU_BOOKS else None

    chunks = []
    for section in sections:
        if not section["paragraphs"]:
            continue
        for seq, (text, start_page, _end_page) in enumerate(
            _pack_paragraphs(section["paragraphs"]), start=1
        ):
            printed_page = _compute_printed_page(document_id, start_page, sadiku_offset)
            chunks.append(
                {
                    "chunk_id": _build_chunk_id(
                        document_id, section["chapter_number"], section["section_number"],
                        printed_page if printed_page is not None else start_page, seq,
                    ),
                    "document_id": document_id,
                    "book_title": book_meta["book_title"],
                    "edition": book_meta.get("edition"),
                    "authors": book_meta["authors"],
                    "subject": book_meta["subject"],
                    "course_level": book_meta["course_level"],
                    "language": book_meta["language"],
                    "source_url": book_meta.get("source_url"),
                    "license": book_meta["license"],
                    "retrieved_date": book_meta["retrieved_date"],
                    "chapter_number": section["chapter_number"],
                    "chapter_title": section["chapter_title"],
                    "section_number": section["section_number"],
                    "section_title": section["section_title"],
                    "page_number": start_page,
                    "printed_page": printed_page,
                    "content_type": "concept",
                    "difficulty": None,
                    "learning_objective": None,
                    "prerequisites": None,
                    "keywords": None,
                    "text": text,
                }
            )
    return chunks
