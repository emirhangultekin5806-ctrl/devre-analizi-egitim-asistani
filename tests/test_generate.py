import pytest

from app.rag.generate import (
    DEFAULT_TIER,
    TASK_TIERS,
    TIERS,
    _format_context,
    _is_prose,
    _split_sentences,
    resolve_tier,
)


def test_format_context_includes_book_and_chapter_label():
    hits = [
        {
            "text": "Ohm's law states V=IR.",
            "metadata": {
                "book_title": "Fundamentals of Electric Circuits",
                "chapter_number": 2,
                "chapter_title": "Basic Laws",
            },
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


# --- Cumle ayirma / duz yazi filtresi (spec disi, PDF gurultusune karsi) ---


def test_split_sentences_normalizes_pdf_line_breaks():
    # Ham chunk metni PDF satir kaydirmalari iceriyor; bunlar tek bosluga
    # indirgenmezse hem secim hem esleme bozuluyor.
    text = "Current enters the node from the left side.\nThe sum of all\ncurrents is zero here."
    sentences = _split_sentences(text)
    assert sentences[0] == "Current enters the node from the left side."
    assert "\n" not in sentences[1]


def test_split_sentences_drops_figure_captions():
    text = "Figure 4.23 Replacing a linear two-terminal circuit by its equivalent."
    assert _split_sentences(text) == []


def test_split_sentences_keeps_real_prose():
    text = "The sum of all currents entering and exiting a node must sum to zero."
    assert _split_sentences(text) == [text]


def test_is_prose_rejects_equation_fragment():
    assert _is_prose("4.24(b); that is, (4.7) RTh  Rin RTh RTh a-b a-b") is False


def test_is_prose_rejects_too_few_words():
    assert _is_prose("A transient analysis.") is False


def test_is_prose_accepts_normal_sentence():
    assert _is_prose("Capacitance is directly proportional to the plate area.") is True


# --- Model kademeleri ---


def test_resolve_tier_uses_task_default():
    assert resolve_tier(task="quiz") == TIERS[TASK_TIERS["quiz"]]
    assert resolve_tier(task="hint") == TIERS[TASK_TIERS["hint"]]


def test_resolve_tier_explicit_overrides_task():
    # Gelismis ayar: gorevin varsayilanini elle gecersiz kilma
    assert resolve_tier(tier="fast", task="quiz") == TIERS["fast"]


def test_resolve_tier_falls_back_to_default_for_unknown_task():
    assert resolve_tier(task="bilinmeyen_gorev") == TIERS[DEFAULT_TIER]


def test_resolve_tier_rejects_unknown_tier():
    with pytest.raises(ValueError, match="Bilinmeyen kademe"):
        resolve_tier(tier="ultra")


def test_every_tier_sets_think_explicitly():
    # gemma4 varsayilan olarak gizli "thinking" calistiriyor (244 token /
    # 30.7s vs 2 token / 4.2s). Kademeler bunu asla varsayilana birakmamali.
    for name, config in TIERS.items():
        assert "think" in config, f"{name} kademesinde 'think' belirtilmemis"
        assert "model" in config
