"""Elle dogrulanmis cevapla karsilastirma: sessiz yanlis cevabi yakalamali."""
from scripts.check_ground_truth import compare


def _report(*values):
    return {"status": "ok", "elements": [{"kind": k, "value": v} for k, v in values]}


def test_missing_component_is_caught_even_when_the_circuit_solved():
    """OLCULDU (1-100/65.png): 6 direncin 2'si bulundu, devre yine 'cozuldu'."""
    truth = {"verdict": "solvable", "components": {"resistor": [5, 10, 50, 40]}}
    problems = compare(truth, _report(("resistor", 10), ("resistor", 50)))
    assert problems and "5" in problems[0] and "40" in problems[0]


def test_out_of_scope_circuit_must_not_solve():
    """OLCULDU (1-100/31.png): degerler dogru okundu ama karsilikli enduktans
    modellenmedigi icin 'cozuldu' demek yanlis cevap uretmek demek."""
    truth = {"verdict": "out_of_scope", "sebep": "karsilikli enduktans"}
    assert compare(truth, {"status": "ok", "elements": []})
    assert compare(truth, {"status": "fail", "reason": "..."}) == []


def test_exact_match_is_clean_and_tolerance_does_not_swallow_a_factor_of_ten():
    truth = {"verdict": "solvable", "components": {"resistor": [7500], "voltage_source": [20]}}
    assert compare(truth, _report(("resistor", 7500.0), ("voltage_source", 20.0))) == []
    assert compare(truth, _report(("resistor", 750.0), ("voltage_source", 20.0)))
