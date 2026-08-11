import json
from pathlib import Path

from app.chunking.chunk_builder import (
    _build_chunk_id,
    _pack_paragraphs,
    build_chunks_for_book,
)
from app.chunking.segment import build_segments

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC_PROCESSED = ROOT / "data" / "processed" / "fiore_dc.jsonl"


def _page(page_number, chapter_number, section_number, clean_text,
          chapter_title="Ch", section_title="Sec"):
    return {
        "page_number": page_number,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "section_number": section_number,
        "section_title": section_title,
        "clean_text": clean_text,
    }


def test_build_segments_excludes_pages_without_chapter_number():
    pages = [
        _page(0, None, None, "TOC icerigi burada"),
        _page(1, 1, "1.1", "Gercek icerik burada"),
    ]
    sections = build_segments(pages)
    assert len(sections) == 1
    assert sections[0]["chapter_number"] == 1


def test_build_segments_never_mixes_two_sections():
    # spec kural 2: bolum/alt bolum sinirlari korunmali
    pages = [
        _page(0, 1, "1.1", "Birinci section metni."),
        _page(1, 1, "1.2", "Ikinci section metni."),
    ]
    sections = build_segments(pages)
    assert len(sections) == 2
    assert sections[0]["section_number"] == "1.1"
    assert sections[1]["section_number"] == "1.2"
    assert "Birinci" in sections[0]["paragraphs"][0][0]
    assert "Ikinci" in sections[1]["paragraphs"][0][0]


def test_build_segments_keeps_multi_page_section_as_one_block():
    pages = [
        _page(0, 1, "1.1", "Ilk sayfa."),
        _page(1, 1, "1.1", "Ikinci sayfa, ayni section."),
    ]
    sections = build_segments(pages)
    assert len(sections) == 1
    assert len(sections[0]["paragraphs"]) == 2


def test_pack_paragraphs_splits_when_target_exceeded():
    long_para = "kelime " * 200  # ~350 token tahmini
    paragraphs = [(long_para, 0), (long_para, 0), (long_para, 0)]
    packed = _pack_paragraphs(paragraphs)
    assert len(packed) >= 2


def test_pack_paragraphs_merges_small_tail_into_previous_chunk():
    long_para = "kelime " * 200
    tiny_para = "kisa."
    paragraphs = [(long_para, 0), (long_para, 0), (tiny_para, 0)]
    packed = _pack_paragraphs(paragraphs)
    assert tiny_para in packed[-1][0]


def test_chunk_id_format():
    chunk_id = _build_chunk_id("fiore_dc", 2, "2.5", 40, 1)
    assert chunk_id == "fiore_dc_ch2_s25_p40_c01"


def test_chunk_id_handles_missing_section_number():
    chunk_id = _build_chunk_id("fiore_dc", 1, None, 10, 1)
    assert chunk_id == "fiore_dc_ch1_s0_p10_c01"


REQUIRED_SCHEMA_FIELDS = {
    "chunk_id", "document_id", "book_title", "edition", "authors", "subject",
    "course_level", "language", "source_url", "license", "retrieved_date",
    "chapter_number", "chapter_title", "section_number", "section_title",
    "page_number", "printed_page", "content_type", "difficulty",
    "learning_objective", "prerequisites", "keywords", "text",
}


def test_real_fiore_dc_chunks_have_full_schema_and_unique_ids():
    with FIORE_DC_PROCESSED.open(encoding="utf-8") as f:
        pages = [json.loads(line) for line in f]

    chunks = build_chunks_for_book(pages, "fiore_dc")

    assert len(chunks) > 0
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))  # chunk_id benzersiz (spec gereksinimi)

    for chunk in chunks:
        assert REQUIRED_SCHEMA_FIELDS <= set(chunk.keys())
        assert chunk["chapter_number"] is not None
        assert chunk["content_type"] == "concept"  # bu turda hep concept
        assert len(chunk["text"]) > 0
