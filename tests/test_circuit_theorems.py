"""Süperpozisyon ve Thevenin/Norton testleri -- Devre Teoremleri (Sadiku Böl. 4).

Beklenen değerler kitabın kendi ÇÖZÜLMÜŞ örneklerinden (Example 4.3,
Example 4.9) -- devre elle kurulup topoloji o örneklerin metninden/mesh
denklemlerinden türetildi, sonuç kitabın basılı cevabıyla karşılaştırıldı.
Bağımlı-kaynaklı Thevenin testi ("negatif direnç") kitabın kendi teorik
iddiasının (§4.5: "R_th negatif olabilir, bu devre güç sağladığı anlamına
gelir") elle doğrulanmış sayısal bir örneği -- belirli bir örnek numarasına
değil, formüle dayanıyor (bkz. test_circuit_ac.py'deki aynı yaklaşım).
"""

import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError
from app.circuit.theorems import (
    kill_independent_sources,
    superposition,
    thevenin_equivalent,
)


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


def I(name, a, b, value):
    return Element(name, "current_source", (a, b), value)


# --- kaynak öldürme ----------------------------------------------------------


def test_killing_zeroes_independent_sources_but_keeps_the_element():
    net = Netlist([V("s", "a", "gnd", 10.0), I("i1", "gnd", "a", 2.0), R("1", "a", "gnd", 5.0)])
    killed = kill_independent_sources(net)
    assert killed.by_name("s").value == 0.0
    assert killed.by_name("i1").value == 0.0
    assert killed.by_name("1").value == 5.0  # direnç etkilenmez


def test_killing_never_touches_dependent_sources():
    """Kontrol değişkeni devrenin geri kalanından geldiği için bağımlı
    kaynaklar öldürülemez (kitabın kendi uyarısı, §4.5)."""
    net = Netlist(
        [
            R("1", "a", "x", 2.0),
            Element("E1", "vcvs", ("x", "gnd"), 3.0, control_nodes=("a", "x")),
        ]
    )
    killed = kill_independent_sources(net)
    assert killed.by_name("E1").value == 3.0
    assert killed.by_name("E1").control_nodes == ("a", "x")


# --- süperpozisyon: Sadiku Example 4.3 ---------------------------------------
#
# Devre: 6V kaynak -- 8Ω -- düğüm A -- 4Ω -- toprak; 3A kaynağı düğüm A'ya
# enjekte ediyor. v = V(A). Kitap: 6V tek başına v1=2V, 3A tek başına
# v2=8V, toplam v=10V.
_EXAMPLE_4_3 = [
    V("Vs", "ns", "gnd", 6.0),
    R("R8", "ns", "na", 8.0),
    R("R4", "na", "gnd", 4.0),
    I("Is", "gnd", "na", 3.0),
]


def test_superposition_matches_example_4_3():
    result = superposition(Netlist(list(_EXAMPLE_4_3)), "R4")
    by_source = {term.source_name: term.voltage for term in result.terms}
    assert by_source["Vs"] == pytest.approx(2.0, rel=1e-6)
    assert by_source["Is"] == pytest.approx(8.0, rel=1e-6)
    assert result.total_voltage == pytest.approx(10.0, rel=1e-6)


def test_superposition_total_matches_the_real_circuit():
    """Süperpozisyonun matematiksel garantisi: katkıların toplamı, TÜM
    kaynaklar aktifken hesaplanan gerçek değere birebir eşit olmalı."""
    result = superposition(Netlist(list(_EXAMPLE_4_3)), "R4")
    assert result.actual_voltage == pytest.approx(10.0, rel=1e-6)
    assert result.matches_actual()


def test_superposition_requires_at_least_two_independent_sources():
    net = Netlist([V("s", "a", "gnd", 10.0), R("1", "a", "gnd", 5.0)])
    with pytest.raises(SolverError, match="en az 2"):
        superposition(net, "1")


# --- Thevenin/Norton: Sadiku Example 4.9 (Figure 4.28) -----------------------
#
# Devre: 32V -- 4Ω -- düğüm X; X -- 12Ω -- toprak; 2A kaynağı topraktan
# X'e; X -- 1Ω -- terminal a; b = toprak. Kitap: V_th=30V, R_th=4Ω
# (1Ω + 4Ω∥12Ω = 1+3 = 4Ω).
_EXAMPLE_4_9 = [
    V("V1", "ny", "gnd", 32.0),
    R("R4", "ny", "nx", 4.0),
    R("R12", "nx", "gnd", 12.0),
    I("I2", "gnd", "nx", 2.0),
    R("R1", "nx", "a", 1.0),
]


def test_thevenin_matches_example_4_9():
    result = thevenin_equivalent(Netlist(list(_EXAMPLE_4_9)), "a", "gnd")
    assert result.v_th == pytest.approx(30.0, rel=1e-6)
    assert result.r_th == pytest.approx(4.0, rel=1e-6)


def test_norton_current_equals_v_th_over_r_th():
    result = thevenin_equivalent(Netlist(list(_EXAMPLE_4_9)), "a", "gnd")
    assert result.i_norton == pytest.approx(30.0 / 4.0, rel=1e-6)


def test_thevenin_probe_does_not_leak_into_the_original_netlist():
    original = Netlist(list(_EXAMPLE_4_9))
    thevenin_equivalent(original, "a", "gnd")
    assert {e.name for e in original.elements} == {"V1", "R4", "R12", "I2", "R1"}


# --- Thevenin direnci bağımlı kaynakla: kitabın "negatif direnç" iddiası ----
#
# Sadiku §4.5: "R_th takes a negative value... this is possible in a
# circuit with dependent sources; Example 4.10 will illustrate this."
# Burada VCVS'in kazancı R1 * (1+K) (aynı yönde) ya da R1 * (1-K) (zıt
# yönde) verir -- ikinci durumda K>1 iken R_th negatif çıkar. Elle
# doğrulanmış temel devre teorisi (belirli bir örnek numarasına dayanmıyor,
# bkz. dosya docstring'i).
def _rth_with_vcvs(control_nodes):
    net = Netlist(
        [
            R("R1", "a", "x", 2.0),
            Element("E1", "vcvs", ("x", "gnd"), 3.0, control_nodes=control_nodes),
        ]
    )
    return thevenin_equivalent(net, "a", "gnd").r_th


def test_r_th_stays_correct_with_an_aiding_dependent_source():
    assert _rth_with_vcvs(("a", "x")) == pytest.approx(2.0 * (1 + 3), rel=1e-6)


def test_r_th_can_go_negative_with_an_opposing_dependent_source():
    """Kitabın kendi iddiası: negatif R_th, devrenin güç SAĞLADIĞI anlamına
    gelir -- bağımlı kaynaklı devrelerde mümkün, bağımsız kaynaklı
    devrelerde asla olmaz."""
    assert _rth_with_vcvs(("x", "a")) == pytest.approx(2.0 * (1 - 3), rel=1e-6)
