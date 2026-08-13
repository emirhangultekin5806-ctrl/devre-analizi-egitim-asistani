import json
from pathlib import Path

import pytest

from app.circuit.problems import Problem, extract_problems, parse_answer_values

ROOT = Path(__file__).resolve().parent.parent
SADIKU_1 = ROOT / "data" / "chunks" / "sadiku_1.jsonl"

skip_no_sadiku = pytest.mark.skipif(
    not SADIKU_1.exists(), reason="sadiku_1 chunk'lari bu makinede yok (telifli)"
)


def chunk(text, chunk_id="c1", document_id="sadiku_1"):
    return {"text": text, "chunk_id": chunk_id, "document_id": document_id}


# --- CEVAP SIZINTISI KORUMASI (en kritik davranis) -------------------------


def test_problem_text_never_contains_the_answer():
    """Sistem cevabi GORMEDEN cozmeli; gorurse dogrulama anlamsizlasir."""
    text = "Practice Problem 1.1\nFind the current.\nAnswer: 7.36 mA.\n"
    problem = extract_problems([chunk(text)])[0]
    assert "Answer" not in problem.text
    assert "7.36" not in problem.text
    assert problem.expected_answer == "7.36 mA."


def test_problem_rejects_construction_with_leaked_answer():
    """Yanlislikla cevap iceren bir metinle Problem uretilemesin."""
    with pytest.raises(ValueError, match="cevap sızıntısı"):
        Problem(
            problem_id="x",
            document_id="d",
            chunk_id="c",
            text="Find i. Answer: 5 A.",
            expected_answer="5 A.",
        )


@skip_no_sadiku
def test_no_extracted_problem_leaks_its_answer_on_real_data():
    with SADIKU_1.open(encoding="utf-8") as f:
        problems = extract_problems([json.loads(line) for line in f])
    assert problems, "gercek veriden alistirma cikmali"
    for problem in problems:
        assert "answer" not in problem.text.lower()


# --- cikarma kurallari -----------------------------------------------------


def test_skips_problem_without_answer():
    assert extract_problems([chunk("Practice Problem 3.1\nFind R.")]) == []


def test_skips_chunk_without_problem_heading():
    assert extract_problems([chunk("Some prose.\nAnswer: 5 A.")]) == []


def test_answer_is_limited_to_one_line():
    """Gercek veride cevabin ardindan baska icerik geliyor; ona tasmamali."""
    text = "Practice Problem 1.1\nFind i.\nAnswer: 7.36 mA.\nq = 10e-2t mC, 31.42 mA\n"
    problem = extract_problems([chunk(text)])[0]
    assert problem.expected_answer == "7.36 mA."
    assert problem.values == ((0.00736, "A"),)


def test_answer_on_next_line_is_still_captured():
    text = "Practice Problem 2.3\nFind i and R.\nAnswer:\n5 mA, 2 V\n"
    problem = extract_problems([chunk(text)])[0]
    assert problem.expected_answer == "5 mA, 2 V"


def test_figure_references_are_collected():
    text = "Practice Problem 2.9\nFind Req in Fig. 2.36.\nAnswer: 6 Ω.\n"
    problem = extract_problems([chunk(text)])[0]
    assert problem.figure_refs == ("2.36",)


# --- deger ayristirma ------------------------------------------------------


def test_parses_si_prefix():
    assert parse_answer_values("7.36 mA.") == ((0.00736, "A"),)
    assert parse_answer_values("3.709 kW.") == ((3709.0, "W"),)


def test_parses_multiple_values():
    assert parse_answer_values("(a) 17.27 W, (b) 29.7 W.") == ((17.27, "W"), (29.7, "W"))


def test_distinguishes_seconds_from_siemens():
    """'s' saniye, 'S' siemens -- buyuk/kucuk harf onemli (gercek veride yakalandi)."""
    assert parse_answer_values("16.667 s.") == ((16.667, "s"),)
    assert parse_answer_values("4 S.") == ((4.0, "S"),)


def test_normalizes_ohm_spelling():
    assert parse_answer_values("6 ohm") == ((6.0, "Ω"),)
    assert parse_answer_values("11 Ω") == ((11.0, "Ω"),)


def test_returns_empty_when_no_numeric_answer():
    assert parse_answer_values("Proof.") == ()
