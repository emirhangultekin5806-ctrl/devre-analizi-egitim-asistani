"""`scripts/regression_44.py` karsilastirmasinin dogru tarafi bozuk saymasi."""
from scripts.regression_44 import compare


def test_broke_and_fixed_are_not_swapped():
    baseline = {"a": {"status": "ok"}, "b": {"status": "fail"}, "c": {"status": "ok"}}
    current = {"a": {"status": "fail"}, "b": {"status": "ok"}, "c": {"status": "ok"}}
    assert compare(baseline, current) == (["a"], ["b"])


def test_only_circuits_present_in_both_runs_are_compared():
    """Eksik extraction'i "bozuldu" saymak yanlis alarm uretir."""
    baseline = {"a": {"status": "ok"}, "yok": {"status": "ok"}}
    current = {"a": {"status": "ok"}, "yeni": {"status": "fail"}}
    assert compare(baseline, current) == ([], [])
