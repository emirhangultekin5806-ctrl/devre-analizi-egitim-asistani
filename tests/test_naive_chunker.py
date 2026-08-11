import json
from pathlib import Path

from app.chunking.naive_chunker import build_page_char_spans, naive_fixed_size_chunks

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC_PROCESSED = ROOT / "data" / "processed" / "fiore_dc.jsonl"


def _page(page_number, chapter_number, section_number, clean_text):
    return {
        "page_number": page_number,
        "chapter_number": chapter_number,
        "section_number": section_number,
        "clean_text": clean_text,
    }


def test_naive_chunks_cover_full_text_without_gaps():
    pages = [_page(0, 1, "1.1", "a" * 50)]
    chunks = naive_fixed_size_chunks(pages, target_chars=20)
    assert chunks[0]["start_char"] == 0
    assert chunks[-1]["end_char"] == 50
    for i in range(len(chunks) - 1):
        assert chunks[i]["end_char"] == chunks[i + 1]["start_char"]


def test_naive_chunks_excludes_pages_without_chapter_number():
    pages = [
        _page(0, None, None, "TOC icerigi"),
        _page(1, 1, "1.1", "Gercek icerik"),
    ]
    chunks = naive_fixed_size_chunks(pages, target_chars=100)
    assert "TOC" not in chunks[0]["text"]
    assert "Gercek icerik" in chunks[0]["text"]


def test_naive_chunker_ignores_section_boundary_by_construction():
    # spec kural 2'yi bilerek ihlal eden strateji: iki farkli section'in
    # metni ayni pencereye dusebiliyor, cunku yapidan tamamen habersiz.
    pages = [
        _page(0, 1, "1.1", "Birinci section metni burada uzun bir sekilde devam ediyor."),
        _page(1, 1, "1.2", "Ikinci section metni de hemen ardindan geliyor."),
    ]
    chunks = naive_fixed_size_chunks(pages, target_chars=1000)
    assert len(chunks) == 1
    assert "Birinci" in chunks[0]["text"] and "Ikinci" in chunks[0]["text"]


def test_build_page_char_spans_matches_concatenation_order():
    pages = [
        _page(0, 1, "1.1", "abc"),
        _page(1, 1, "1.2", "defgh"),
    ]
    spans = build_page_char_spans(pages)
    assert spans[0]["start_char"] == 0
    assert spans[0]["end_char"] == 3
    assert spans[1]["start_char"] == 5  # "abc" + "\n\n" ayraci
    assert spans[1]["end_char"] == 10


def test_real_fiore_dc_naive_strategy_produces_section_boundary_violations():
    """Yapi-farkinda stratejinin (test_chunk_builder.py) 0 ihlal ile
    kontrastini gercek veride kanitlar -- naive strateji spec kural 2'yi
    duzenli olarak ihlal ediyor, bu yuzden nihai cozum olamaz."""
    with FIORE_DC_PROCESSED.open(encoding="utf-8") as f:
        pages = [json.loads(line) for line in f]

    chunks = naive_fixed_size_chunks(pages)
    spans = build_page_char_spans(pages)

    def sections_touched(chunk):
        touched = set()
        for span in spans:
            if span["start_char"] < chunk["end_char"] and span["end_char"] > chunk["start_char"]:
                touched.add((span["chapter_number"], span["section_number"]))
        return touched

    violations = sum(1 for c in chunks if len(sections_touched(c)) > 1)
    assert violations > 0
