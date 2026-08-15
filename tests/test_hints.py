import pytest

from app.hints.generate import (
    _FALLBACK_EVALUATION,
    MAX_HINT_LEVEL,
    VERDICTS,
    _parse_evaluation,
    _parse_question,
    generate_hint,
)

# --- _parse_question ---------------------------------------------------------


def test_parses_valid_question():
    assert _parse_question('{"soru": "KCL neyi ifade eder?"}') == "KCL neyi ifade eder?"


def test_question_ignores_text_around_json():
    raw = 'Iste soru:\n{"soru": "Ohm yasasi nedir?"}\nUmarim yardimci olur.'
    assert _parse_question(raw) == "Ohm yasasi nedir?"


def test_question_returns_none_when_no_json():
    assert _parse_question("Uzgunum, soru uretemedim.") is None


def test_question_returns_none_on_malformed_json():
    assert _parse_question('{"soru": ') is None


def test_question_returns_none_for_empty_question():
    assert _parse_question('{"soru": "  "}') is None
    assert _parse_question("{}") is None


# --- _parse_evaluation --------------------------------------------------------


def test_parses_valid_evaluation():
    raw = '{"degerlendirme": "kismen_dogru", "aciklama": "Tanim dogru ama formul eksik."}'
    result = _parse_evaluation(raw)
    assert result == {"degerlendirme": "kismen_dogru", "aciklama": "Tanim dogru ama formul eksik."}


def test_evaluation_ignores_text_around_json():
    raw = 'Degerlendirme:\n{"degerlendirme": "dogru", "aciklama": "Eksiksiz."}\nTesekkurler.'
    assert _parse_evaluation(raw)["degerlendirme"] == "dogru"


@pytest.mark.parametrize("verdict", sorted(VERDICTS))
def test_all_verdicts_are_accepted(verdict):
    raw = f'{{"degerlendirme": "{verdict}", "aciklama": "x"}}'
    assert _parse_evaluation(raw)["degerlendirme"] == verdict


def test_evaluation_falls_back_on_unknown_verdict():
    """Model gecersiz bir deger uydurursa (VERDICTS disi), sessizce
    'dogru' sanilmamali -- guvenli geri dususe (yetersiz) dusmeli."""
    raw = '{"degerlendirme": "harika", "aciklama": "..."}'
    assert _parse_evaluation(raw) == _FALLBACK_EVALUATION


def test_evaluation_falls_back_on_missing_json():
    assert _parse_evaluation("Bir sorun oldu.") == _FALLBACK_EVALUATION


def test_evaluation_falls_back_on_malformed_json():
    assert _parse_evaluation('{"degerlendirme": ') == _FALLBACK_EVALUATION


def test_evaluation_defaults_missing_explanation_to_empty_string():
    result = _parse_evaluation('{"degerlendirme": "yanlis"}')
    assert result == {"degerlendirme": "yanlis", "aciklama": ""}


# --- generate_hint seviye sınırı ---------------------------------------------


@pytest.mark.parametrize("level", [0, 4, -1])
def test_generate_hint_rejects_out_of_range_level(level):
    with pytest.raises(ValueError, match=str(MAX_HINT_LEVEL)):
        generate_hint("soru", ["kaynak"], "cevap", hint_level=level)
