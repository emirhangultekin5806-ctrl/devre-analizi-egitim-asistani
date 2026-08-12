from app.rag.generate import _format_context, _strip_thinking


def test_format_context_includes_book_and_chapter_label():
    hits = [
        {
            "text": "Ohm's law states V=IR.",
            "metadata": {"book_title": "Fundamentals of Electric Circuits", "chapter_number": 2, "chapter_title": "Basic Laws"},
        }
    ]
    context = _format_context(hits)
    assert "Fundamentals of Electric Circuits" in context
    assert "Bölüm 2" in context
    assert "Ohm's law states V=IR." in context


def test_format_context_numbers_multiple_sources():
    hits = [
        {"text": "birinci", "metadata": {"book_title": "A", "chapter_number": 1, "chapter_title": "X"}},
        {"text": "ikinci", "metadata": {"book_title": "B", "chapter_number": 2, "chapter_title": "Y"}},
    ]
    context = _format_context(hits)
    assert "Kaynak 1" in context
    assert "Kaynak 2" in context


def test_strip_thinking_removes_think_block():
    text = "<think>uzun ic akil yurutme burada</think>Kısa net cevap."
    assert _strip_thinking(text) == "Kısa net cevap."


def test_strip_thinking_handles_multiline_think_block():
    text = "<think>\nsatir 1\nsatir 2\n</think>\nCevap burada."
    assert _strip_thinking(text) == "Cevap burada."


def test_strip_thinking_no_op_when_no_think_block():
    text = "Doğrudan cevap, think bloğu yok."
    assert _strip_thinking(text) == text
