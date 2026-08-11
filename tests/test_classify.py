from app.chunking.classify import (
    classify_paragraph,
    group_by_content_type,
    split_embedded_headings,
)


def test_classify_example_heading():
    text = "Example 1.2\nPerform the following computation."
    assert classify_paragraph(text) == "example"


def test_classify_practice_problem_heading():
    text = "Practice Problem 1.2\nFind the current."
    assert classify_paragraph(text) == "practice_problem"


def test_classify_learning_objectives_heading():
    text = "1.0 Chapter Learning Objectives\nAfter completing this chapter..."
    assert classify_paragraph(text) == "learning_objectives"


def test_classify_summary_heading_fiore_style():
    text = "1.8 Summary\nAn electrical system is one that..."
    assert classify_paragraph(text) == "chapter_summary"


def test_classify_summary_heading_sadiku_style():
    text = "Summary\n1. Two coils are said to be mutually coupled."
    assert classify_paragraph(text) == "chapter_summary"


def test_classify_summary_prefix_is_not_chapter_summary():
    # "Summary of ..." bir alt-basliktir, chapter summary degildir (spec kural
    # disi bir bolum-ici recap) -- gercek Sadiku verisinde bulundu.
    text = "Summary of Bode straight-line magnitude plots\nSome table follows."
    assert classify_paragraph(text) != "chapter_summary"


def test_classify_regular_text_is_concept():
    assert classify_paragraph("Resistance opposes current flow.") == "concept"


def test_split_embedded_headings_breaks_fused_paragraph():
    # Gercek veride sik gorulen durum: baslik satiri bir onceki cumlenin
    # hemen ardina, bos satir olmadan yapisik geliyor.
    paragraphs = [
        ("...cannot trust the odometer.\nExample 1.2\nPerform the computation.", 5),
    ]
    result = split_embedded_headings(paragraphs)
    assert len(result) == 2
    assert result[0][0] == "...cannot trust the odometer."
    assert result[1][0].startswith("Example 1.2")
    assert result[0][1] == 5 and result[1][1] == 5


def test_split_embedded_headings_no_heading_stays_single_paragraph():
    paragraphs = [("Just regular narrative text.", 3)]
    result = split_embedded_headings(paragraphs)
    assert result == paragraphs


def test_group_by_content_type_splits_on_type_change():
    paragraphs = [
        ("Some concept text.", 1),
        ("More concept text.", 1),
        ("Example 1.1\nSolve for current.", 2),
        ("Back to concept text.", 3),
    ]
    blocks = group_by_content_type(paragraphs)
    assert [b[0] for b in blocks] == ["concept", "example", "concept"]
    assert len(blocks[0][1]) == 2
    assert len(blocks[1][1]) == 1
    assert len(blocks[2][1]) == 1


def test_group_by_content_type_example_continuation_without_own_heading_becomes_concept():
    # Bilinen/kabul edilen sinirlama: bir Example'in devam paragrafi kendi
    # basligini tasimiyorsa classify_paragraph onu "concept" sayar, bu da
    # yeni bir blok acar (ornegin cozumu ile ayni chunk'ta kalmayabilir).
    paragraphs = [
        ("Example 1.1\nProblem statement.", 2),
        ("Solution step continues here.", 2),
    ]
    blocks = group_by_content_type(paragraphs)
    assert [b[0] for b in blocks] == ["example", "concept"]
