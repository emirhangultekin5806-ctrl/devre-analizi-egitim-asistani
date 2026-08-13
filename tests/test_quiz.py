from app.quiz.generate import _parse_quiz

VALID_ITEM = """[
  {"soru": "KCL neyi ifade eder?",
   "secenekler": {"A": "Dugume giren akimlarin toplami sifirdir",
                  "B": "Gerilim sabittir", "C": "Direnc artar", "D": "Guc sifirdir"},
   "dogru": "A",
   "kanit": "Kirchhoff's current law states that the algebraic sum of currents is zero."}
]"""


def test_parses_valid_question():
    result = _parse_quiz(VALID_ITEM, 5)
    assert len(result) == 1
    assert result[0]["dogru"] == "A"
    assert set(result[0]["secenekler"]) == {"A", "B", "C", "D"}
    assert result[0]["kanit"].startswith("Kirchhoff")


def test_ignores_text_around_json():
    # Model bazen JSON'un onune/arkasina aciklama yaziyor.
    raw = "Iste sorular:\n" + VALID_ITEM + "\nUmarim yardimci olur."
    assert len(_parse_quiz(raw, 5)) == 1


def test_returns_empty_when_no_json():
    assert _parse_quiz("Uzgunum, soru uretemedim.", 5) == []


def test_returns_empty_on_malformed_json():
    assert _parse_quiz('[{"soru": "eksik", ', 5) == []


def test_drops_question_with_missing_option():
    raw = """[{"soru": "x", "secenekler": {"A": "a", "B": "b", "C": "c"}, "dogru": "A"}]"""
    assert _parse_quiz(raw, 5) == []


def test_drops_question_whose_answer_is_not_an_option():
    raw = """[{"soru": "x",
      "secenekler": {"A": "a", "B": "b", "C": "c", "D": "d"}, "dogru": "E"}]"""
    assert _parse_quiz(raw, 5) == []


def test_drops_question_with_empty_option_text():
    raw = """[{"soru": "x",
      "secenekler": {"A": "a", "B": "", "C": "c", "D": "d"}, "dogru": "A"}]"""
    assert _parse_quiz(raw, 5) == []


def test_respects_question_count_limit():
    one = VALID_ITEM.strip()[1:-1]  # dis koseli parantezleri at
    raw = "[" + ",".join([one] * 6) + "]"
    assert len(_parse_quiz(raw, 3)) == 3
