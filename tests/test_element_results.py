import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import element_results, power_balance, solve_dc


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


def I(name, a, b, value):
    return Element(name, "current_source", (a, b), value)


DIVIDER = [V("s", "vs", "gnd", 10), R("1", "vs", "mid", 5), R("2", "mid", "gnd", 5)]

REAL_CIRCUIT = [
    V("s", "vs", "gnd", 24),
    R("6", "vs", "n1", 4),
    R("1", "n1", "gnd", 12),
    R("2", "n1", "n2", 8),
    R("3", "n2", "gnd", 12),
    R("4", "n2", "n3", 4),
    R("5", "n3", "gnd", 2),
]


def results_for(elements):
    net = Netlist(list(elements))
    return net, element_results(net, solve_dc(net))


# --- eleman bazli buyuklukler ----------------------------------------------


def test_resistor_current_follows_ohms_law():
    _, results = results_for(DIVIDER)
    # 10 V, 5+5 ohm -> 1 A, her direncte 5 V
    assert results["1"].current == pytest.approx(1.0, rel=1e-6)
    assert results["1"].voltage == pytest.approx(5.0, rel=1e-6)


def test_resistor_power_is_v_times_i():
    _, results = results_for(DIVIDER)
    r1 = results["1"]
    assert r1.power == pytest.approx(r1.voltage * r1.current, rel=1e-9)
    assert r1.power == pytest.approx(5.0, rel=1e-6)


def test_resistors_absorb_and_sources_deliver():
    """Pasif isaret kurali: direnc P>0 (harciyor), kaynak P<0 (veriyor)."""
    _, results = results_for(REAL_CIRCUIT)
    assert results["s"].power < 0
    for name in ("1", "2", "3", "4", "5", "6"):
        assert results[name].power > 0


def test_series_elements_share_the_same_current():
    """R4 ve R5 seri -> ayni akim gecmeli."""
    _, results = results_for(REAL_CIRCUIT)
    assert results["4"].current == pytest.approx(results["5"].current, rel=1e-6)


def test_parallel_elements_share_the_same_voltage():
    """R1, kaynagin gordugu n1-gnd gerilimini tasiyor."""
    _, results = results_for(REAL_CIRCUIT)
    assert results["1"].voltage == pytest.approx(14.4, rel=1e-6)


def test_current_source_current_is_its_value():
    _, results = results_for([I("i1", "gnd", "a", 2), R("1", "a", "gnd", 5)])
    assert results["i1"].current == pytest.approx(2.0, rel=1e-6)


# --- guc dengesi (bagimsiz tutarlilik kontrolu) ----------------------------


def test_power_balance_is_zero():
    """Tellegen: harcanan guc = verilen guc. Cozum bozuksa bu tutmaz."""
    _, results = results_for(REAL_CIRCUIT)
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


def test_source_power_equals_total_dissipation():
    _, results = results_for(REAL_CIRCUIT)
    delivered = abs(results["s"].power)
    dissipated = sum(r.power for r in results.values() if r.power > 0)
    assert delivered == pytest.approx(dissipated, rel=1e-9)
    assert delivered == pytest.approx(24 * 2.4, rel=1e-6)


def test_power_balance_holds_with_current_source():
    _, results = results_for(
        [V("s", "a", "gnd", 12), R("1", "a", "b", 3), R("2", "b", "gnd", 6), I("i1", "gnd", "b", 1)]
    )
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


def test_describe_is_student_readable():
    _, results = results_for(DIVIDER)
    text = results["1"].describe()
    assert "I =" in text and "V =" in text and "P =" in text
    assert "harcıyor" in text
