from pathlib import Path

import pytest

from app.ingestion.pdf_extract import extract_pages
from app.ingestion.structure_detect import detect_structure_fiore, detect_structure_sadiku

SADIKU_1 = Path(r"C:\Users\Sinemis\OneDrive\Masaüstü\ilovepdf_split\Devre analizi-1.pdf")
SADIKU_2 = Path(r"C:\Users\Sinemis\OneDrive\Masaüstü\ilovepdf_split\Devre analizi-2.pdf")

skip_no_sadiku_1 = pytest.mark.skipif(not SADIKU_1.exists(), reason="Sadiku vol1 PDF bu makinede yok")
skip_no_sadiku_2 = pytest.mark.skipif(not SADIKU_2.exists(), reason="Sadiku vol2 PDF bu makinede yok")


def _pages(raw_texts: list[str]) -> list[dict]:
    return [{"page_number": i, "raw_text": text} for i, text in enumerate(raw_texts)]


# --- Fiore ---


def test_fiore_basic_chapter_and_section_carry_forward():
    pages = _pages(
        [
            "1 1 Fundamentals\nFundamentals\n1.1 Introduction\n1.1 Introduction\nBody text.",
        ]
    )
    result = detect_structure_fiore(pages)
    assert result[0]["chapter_number"] == 1
    assert result[0]["chapter_title"] == "Fundamentals"
    assert result[0]["section_number"] == "1.1"
    assert result[0]["section_title"] == "Introduction"


def test_fiore_wrapped_title_prefers_longer_repeat_line():
    pages = _pages(
        [
            "1 1 Nodal & Mesh Analysis\nNodal & Mesh Analysis, Dependent Sources\nBody.",
        ]
    )
    result = detect_structure_fiore(pages)
    assert result[0]["chapter_number"] == 1
    assert result[0]["chapter_title"] == "Nodal & Mesh Analysis, Dependent Sources"


def test_fiore_missing_first_letter_still_matches():
    pages = _pages(
        [
            "1 1 Resonance\nesonance\nBody.",
        ]
    )
    result = detect_structure_fiore(pages)
    assert result[0]["chapter_number"] == 1
    assert result[0]["chapter_title"] == "Resonance"


def test_fiore_out_of_order_chapter_number_rejected():
    """Cevap anahtarı ekinde görülen 'N Başlık' tekrarları, ardışık olmayan
    bölüm no'suna sahipse gerçek bölüm geçişi sayılmamalı."""
    pages = _pages(
        [
            "1 1 Fundamentals\nFundamentals\nBody.",
            "9 Inductors\nInductors\nAnswer key text.",
        ]
    )
    result = detect_structure_fiore(pages)
    assert result[0]["chapter_number"] == 1
    assert result[1]["chapter_number"] == 1  # 9 kabul edilmedi, 1 taşındı
    assert result[1]["chapter_title"] == "Fundamentals"


def test_fiore_section_carried_forward_across_pages():
    pages = _pages(
        [
            "1 1 Fundamentals\nFundamentals\n1.1 Introduction\n1.1 Introduction\nBody.",
            "More body text with no new heading.",
        ]
    )
    result = detect_structure_fiore(pages)
    assert result[1]["chapter_number"] == 1
    assert result[1]["section_number"] == "1.1"


# --- Sadiku ---


def test_sadiku_splash_confirmed_by_reinforcement():
    pages = _pages(
        [
            "c h a p t e r\n1\nSome inspirational quote line.",
            "Random body filler with no heading pattern.",
            "5\nChapter 1\nBasic Concepts",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[0]["chapter_number"] == 1
    assert result[0]["chapter_title"] == "Basic Concepts"
    assert result[1]["chapter_number"] == 1  # taşındı
    assert result[2]["chapter_number"] == 1


def test_sadiku_splash_without_reinforcement_rejected():
    """Guided Tour tanıtım sayfasının gerçek bir splash sayfasını birebir
    içermesi gibi durumları modelliyor: ardından gerçek bölüm içeriği
    gelmiyorsa aday reddedilmeli."""
    pages = _pages(
        [
            "Some front-matter filler.",
            "c h a p t e r\n9\nReproduced quote from Guided Tour section.",
            "More filler, no verso/recto reinforcement anywhere nearby.",
            "Still no reinforcement.",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert all(p["chapter_number"] is None for p in result)


def test_sadiku_bootstrap_does_not_assume_chapter_one():
    """sadiku_2 (AC cilt) ilk bölümü 13'ten başlıyor; sabit '1'den başlama
    varsayımı olmamalı."""
    pages = _pages(
        [
            "c h a p t e r\n13\nSome inspirational quote line.",
            "8\nChapter 13\nMagnetically Coupled Circuits",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[0]["chapter_number"] == 13
    assert result[0]["chapter_title"] == "Magnetically Coupled Circuits"


def test_sadiku_recto_section_requires_matching_major_and_real_word():
    pages = _pages(
        [
            "c h a p t e r\n1\nSome inspirational quote line.",
            "5\nChapter 1\nBasic Concepts",
            "1.5\n1024\n8",  # sahte: başlık kelime içermiyor (sayısal tablo)
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[2]["section_number"] is None


def test_sadiku_recto_section_updates_when_valid():
    pages = _pages(
        [
            "c h a p t e r\n1\nSome inspirational quote line.",
            "5\nChapter 1\nBasic Concepts",
            "1.5\nPower and Energy\n11",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[2]["section_number"] == "1.5"
    assert result[2]["section_title"] == "Power and Energy"


def test_sadiku_toc_shaped_input_before_real_chapter_ignored():
    pages = _pages(
        [
            "2\nChapter 1\nBasic Concepts\n3\n1.1\nIntroduction\n4",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[0]["chapter_number"] is None


def test_sadiku_mismatched_verso_chapter_number_does_not_clobber_state():
    pages = _pages(
        [
            "c h a p t e r\n1\nSome inspirational quote line.",
            "5\nChapter 1\nBasic Concepts",
            "9\nChapter 5\nSome Other Chapter Title",
        ]
    )
    result = detect_structure_sadiku(pages)
    assert result[2]["chapter_number"] == 1
    assert result[2]["chapter_title"] == "Basic Concepts"


# --- Gerçek PDF doğrulama (yalnızca bu makinede, dosya varsa) ---


@skip_no_sadiku_1
def test_sadiku_1_real_pdf_reaches_all_twelve_chapters():
    pages = extract_pages(SADIKU_1, "sadiku_1")
    pages = detect_structure_sadiku(pages)
    chapter_numbers = [p["chapter_number"] for p in pages if p["chapter_number"] is not None]
    assert chapter_numbers[0] == 1
    assert max(chapter_numbers) == 12
    assert chapter_numbers == sorted(chapter_numbers)


@skip_no_sadiku_2
def test_sadiku_2_real_pdf_starts_at_thirteen_reaches_nineteen():
    pages = extract_pages(SADIKU_2, "sadiku_2")
    pages = detect_structure_sadiku(pages)
    chapter_numbers = [p["chapter_number"] for p in pages if p["chapter_number"] is not None]
    assert chapter_numbers[0] == 13
    assert max(chapter_numbers) == 19
    assert chapter_numbers == sorted(chapter_numbers)
