from pathlib import Path

from sadiku_pdf import SADIKU_PDF, skip_no_sadiku

from app.ingestion.pdf_extract import extract_pages
from app.ingestion.text_clean import clean_text, clean_text_sadiku, compute_page_offset

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC = ROOT / "data" / "raw" / "open" / "Fiore_DC_Electrical_Circuit_Analysis.pdf"


def test_notes_divider_page_collapses_to_empty_string():
    raw = "Notes\nNotes\n    ♫♫\n    ♫♫\n29\n"
    assert clean_text(raw, page_number=28) == ""


def test_notes_divider_page_no_indent_variant():
    raw = "Notes\nNotes\n♫♫\n♫♫\n43\n"
    assert clean_text(raw, page_number=42) == ""


def test_page_number_footer_line_removed():
    raw = "Some real sentence about circuits.\n51\n"
    result = clean_text(raw, page_number=50)
    assert "51" not in result.split("\n")
    assert "Some real sentence about circuits." in result


def test_standalone_digit_line_not_matching_page_number_is_preserved():
    raw = "31\n10.15\n22\n0.0253\nFigure 2.18\n"
    result = clean_text(raw, page_number=50)  # beklenen sayfa no "51"
    assert "31" in result.split("\n")
    assert "22" in result.split("\n")


def test_toc_dot_leader_lines_removed():
    raw = "3.7 Series Analysis\n.\n.\n.\n.\n.\n.\n.\n.\n  83\n3.8 Potentiometers\n.\n.\n7\n"
    result = clean_text(raw, page_number=6)
    assert "." not in result.split("\n")
    assert "3.7 Series Analysis" in result
    assert "3.8 Potentiometers" in result


def test_mid_body_duplicate_subheading_collapsed():
    raw = "Some text.\nEfficiency\nEfficiency\nMore text.\n"
    result = clean_text(raw, page_number=40)
    assert result.count("Efficiency") == 1


def test_duplicate_separated_by_blank_line_is_not_collapsed():
    raw = "Foo\n\nFoo\n"
    result = clean_text(raw, page_number=0)
    assert result.count("Foo") == 2


def test_long_run_of_duplicate_dot_lines_fully_collapses():
    raw = "Heading\n" + "\n".join(["."] * 50) + "\n99\n"
    result = clean_text(raw, page_number=97)
    assert "." not in result.split("\n")


def test_excess_blank_lines_collapsed_to_one():
    raw = "Paragraph one.\n\n\n\nParagraph two.\n"
    result = clean_text(raw, page_number=0)
    assert "\n\n\n" not in result


def test_page_number_removed_regardless_of_mid_page_position():
    raw = "...wasting 40% of the input power, or 80 watts.\n41\nFigure 2.11\nBasic concept of efficiency.\n"
    result = clean_text(raw, page_number=40)
    lines = result.split("\n")
    assert "41" not in lines
    assert "Figure 2.11" in result


def test_real_example_content_and_formulas_survive_untouched():
    raw = (
        "Example 2.5\n"
        "If a 9 volt battery delivers a current of 0.1 amps, determine the power \n"
        "delivered in watts. \n"
        "P = I×V\n"
        "P = 0.1amps × 9volts\n"
        "P = 0.9W\n"
    )
    result = clean_text(raw, page_number=40)
    assert result == raw.strip()


def test_real_notes_page_28_cleans_to_empty():
    pages = extract_pages(FIORE_DC, "fiore_dc")
    page = pages[28]
    assert clean_text(page["raw_text"], page["page_number"]) == ""
    assert page["raw_text"] != ""


def test_real_example_2_5_page_keeps_content_and_drops_noise():
    pages = extract_pages(FIORE_DC, "fiore_dc")
    page = pages[40]
    result = clean_text(page["raw_text"], page["page_number"])
    assert "Example 2.5" in result
    assert "Example 2.6" in result
    assert result.split("\n").count("Efficiency") == 1
    assert "41" not in result.split("\n")
    assert page["raw_text"].count("Efficiency") == 3  # heading x2 + "Efficiency is the ratio..." cümlesi


# --- Sadiku: compute_page_offset ---


def _sadiku_verso_page(page_number: int, printed: int, chapter: int = 1) -> dict:
    return {
        "page_number": page_number,
        "raw_text": f"{printed}\nChapter {chapter}\nBasic Concepts\n",
    }


def test_compute_page_offset_finds_dominant_offset():
    pages = [_sadiku_verso_page(page_number=n, printed=n - 5) for n in range(6, 21)]
    pages += [_sadiku_verso_page(page_number=n, printed=n - 99) for n in (30, 31)]  # gürültü
    assert compute_page_offset(pages) == 5


def test_compute_page_offset_returns_none_when_signal_too_sparse():
    pages = [_sadiku_verso_page(page_number=n, printed=n - 5) for n in range(6, 9)]  # yalnızca 3 eşleşme
    assert compute_page_offset(pages) is None


def test_compute_page_offset_returns_none_when_no_dominant_winner():
    pages = [_sadiku_verso_page(page_number=n, printed=n - 2) for n in range(12)]
    pages += [_sadiku_verso_page(page_number=n, printed=n - 7) for n in range(20, 32)]
    assert compute_page_offset(pages) is None


def test_compute_page_offset_returns_none_with_no_matches():
    pages = [{"page_number": 0, "raw_text": "No heading pattern here at all."}]
    assert compute_page_offset(pages) is None


# --- Sadiku: clean_text_sadiku ---


def test_clean_text_sadiku_removes_footer_regardless_of_position():
    raw = "Some real sentence.\n18\nMore text after.\n"
    result = clean_text_sadiku(raw, page_number=49, offset=31)  # beklenen basılı no: 18
    assert "18" not in result.split("\n")
    assert "Some real sentence." in result
    assert "More text after." in result


def test_clean_text_sadiku_offset_none_leaves_digit_lines_untouched():
    raw = "Some real sentence.\n18\nMore text after.\n"
    result = clean_text_sadiku(raw, page_number=49, offset=None)
    assert "18" in result.split("\n")


def test_clean_text_sadiku_front_matter_region_left_untouched():
    """expected_printed <= 0 (ön-madde bölgesi) — yanlış tahminle içerik
    bozmaktansa satır silinmeden bırakılır."""
    raw = "Preface text.\n5\n"
    result = clean_text_sadiku(raw, page_number=5, offset=31)  # expected_printed = -26
    assert "5" in result.split("\n")


def test_clean_text_sadiku_does_not_collapse_legitimate_duplicate_lines():
    """Fiore'nin ardışık-aynı-satır birleştirme kuralı Sadiku'ya taşınmadı —
    devre şeması etiketleri (örn. kutup işaretleri) meşru şekilde tekrarlanabilir."""
    raw = "+−\n+−\nBody text.\n"
    result = clean_text_sadiku(raw, page_number=0, offset=None)
    assert result.count("+−") == 2


def test_clean_text_sadiku_excess_blank_lines_collapsed():
    raw = "Paragraph one.\n\n\n\nParagraph two.\n"
    result = clean_text_sadiku(raw, page_number=0, offset=None)
    assert "\n\n\n" not in result


@skip_no_sadiku
def test_compute_page_offset_real_sadiku_is_31():
    pages = extract_pages(SADIKU_PDF, "sadiku_full")
    assert compute_page_offset(pages) == 31


@skip_no_sadiku
def test_single_offset_holds_across_the_whole_book():
    """Kitap eskiden iki cilde bölünmüştü (ofsetleri 31 ve -519); birleşik
    dosyada basılı numaralandırma cilt sınırında kesintisiz devam ettiği
    için TEK bir ofset (31) kitabın sonuna kadar geçerli olmalı.

    Cilt-2 bölgesinden bir sayfanın footer'ının da temizlenebilmesi bunun
    kanıtı: ofset orada tutmasaydı satır silinmezdi.
    """
    pages = extract_pages(SADIKU_PDF, "sadiku_full")
    offset = compute_page_offset(pages)

    page = pages[700]  # cilt-2 bölgesi (eski bölünmede sayfa 150)
    printed = page["page_number"] - offset
    result = clean_text_sadiku(page["raw_text"], page["page_number"], offset)
    assert str(printed) in page["raw_text"].split("\n")
    assert str(printed) not in result.split("\n")


@skip_no_sadiku
def test_clean_text_sadiku_real_page_strips_footer_keeps_body():
    pages = extract_pages(SADIKU_PDF, "sadiku_full")
    offset = compute_page_offset(pages)
    page = pages[45]  # basılı sayfa no "14"
    result = clean_text_sadiku(page["raw_text"], page["page_number"], offset)
    assert "14" not in result.split("\n")
    assert "Chapter 1" in result
    assert "Historical" in result
