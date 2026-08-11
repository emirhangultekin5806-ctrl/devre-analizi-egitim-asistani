"""Sabit karakter/token sayısına dayalı, yapıdan habersiz temel (baseline)
chunking stratejisi.

Yalnızca spec'in açıkça yasakladığı yaklaşımı ("yalnızca sabit karakter
sayısına dayanan chunking nihai çözüm olarak kabul edilmeyecektir") somut
olarak üretip `app/chunking/chunk_builder.py`'deki yapı-farkında stratejiyle
karşılaştırmak için var (bkz. docs/chunking-strateji-karsilastirmasi.md).
Üretim pipeline'ında (`scripts/chunk_books.py`) KULLANILMIYOR.

Bölüm/sayfa sınırlarını hiç bilmez: tüm kitabın `clean_text`'ini tek bir
akışta birleştirip sabit karakter uzunluğunda pencerelere böler. Bir
pencerenin hangi (chapter, section) çiftlerine denk geldiği yalnızca
karşılaştırma ölçümü için `page_spans` ile ayrıca hesaplanır — chunking
mantığının kendisi bu bilgiyi kullanmaz (naive olmasının bütün amacı bu).
"""

CHARS_PER_TOKEN = 4
TARGET_TOKENS = 500
TARGET_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN


def naive_fixed_size_chunks(pages: list[dict], target_chars: int = TARGET_CHARS) -> list[dict]:
    """Dönen: [{chunk_index, text, start_char, end_char}, ...]

    Yalnızca `chapter_number is not None` olan sayfalar dahil edilir (aynı
    ön-madde/answer-key filtresi `segment.py` ile tutarlı olsun diye), ama
    bunun ötesinde hiçbir yapısal bilgi (section, paragraf, başlık) dikkate
    alınmaz — tam olarak `target_chars` uzunluğunda, kelime/paragraf/section
    sınırına bakılmaksızın art arda kesilir.
    """
    content_pages = [p for p in pages if p.get("chapter_number") is not None]
    full_text = "\n\n".join(p.get("clean_text") or "" for p in content_pages)

    chunks = []
    for i, start in enumerate(range(0, len(full_text), target_chars)):
        end = min(start + target_chars, len(full_text))
        chunks.append(
            {
                "chunk_index": i,
                "text": full_text[start:end],
                "start_char": start,
                "end_char": end,
            }
        )
    return chunks


def build_page_char_spans(pages: list[dict]) -> list[dict]:
    """naive_fixed_size_chunks ile AYNI birleştirmeyi tekrar oluşturup her
    sayfanın karakter aralığını (chapter, section) ile birlikte döndürür.
    Yalnızca karşılaştırma/ölçüm amaçlı — chunking'in kendisinin parçası
    değil.
    """
    content_pages = [p for p in pages if p.get("chapter_number") is not None]

    spans = []
    offset = 0
    for page in content_pages:
        text = page.get("clean_text") or ""
        start = offset
        end = start + len(text)
        spans.append(
            {
                "chapter_number": page["chapter_number"],
                "section_number": page.get("section_number"),
                "start_char": start,
                "end_char": end,
            }
        )
        offset = end + 2  # "\n\n" ayracı

    return spans
