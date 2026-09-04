"""Değeri bilinmeyen bir direnci, üzerindeki dal gerilimiyle bulma --
Test Soruları/Soru15 (Sadiku Practice Problem 2.37/Figure 2.101).

Kullanıcı BİLEREK reddetti: bilinmeyen direncin yerine bir kaynak koymak
("yerine kaynak koymak soruyu bozar"). Bu yüzden bu çözüm app/circuit/
solve.py'ye (ngspice/PySpice) HİÇ gitmez -- kendi düğüm gerilimi
denklemlerini (KCL/KVL) kurup çözer.
"""

import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError
from app.circuit.unknown_value import solve_unknown_resistor


def R(name, a, b, value=None):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


def test_soru15_series_loop_finds_2_5_ohm():
    """OLCULDU: kitabın kendi cevabı 2.5 Ω (Figure 2.101). Devre: 20V + 30V
    seri, bilinmeyen R üzerinde 10V düşüyor, bilinen 10Ω ile aynı döngüde."""
    netlist = Netlist([
        V("source_v1", "n0", "n3", 20.0),
        V("source_v2", "n3", "n2", 30.0),
        R("resistor1", "n1", "n2", 10.0),
        R("resistor3", "n0", "n1"),
    ])
    assert solve_unknown_resistor(netlist, "resistor3", 10.0, reference="n0") == pytest.approx(2.5)


def test_sign_of_the_given_branch_voltage_is_not_needed():
    """Dal gerilimi büyüklüğü BİLİNİYOR ama yönü YOK (OCR kutuplama
    işaretini kaybediyor) -- fiziksel kısıt (R negatif olamaz) yönü kendi
    belirlemeli, iki katman geriye BAĞIMSIZ olarak."""
    netlist = Netlist([
        V("source_v1", "n0", "n3", 20.0),
        V("source_v2", "n3", "n2", 30.0),
        R("resistor1", "n1", "n2", 10.0),
        R("resistor3", "n0", "n1"),
    ])
    # nodes[0]/nodes[1] SIRASI degissin -- ayni fiziksel dal, ayni cevap.
    netlist_flipped = Netlist([
        V("source_v1", "n0", "n3", 20.0),
        V("source_v2", "n3", "n2", 30.0),
        R("resistor1", "n1", "n2", 10.0),
        R("resistor3", "n1", "n0"),
    ])
    a = solve_unknown_resistor(netlist, "resistor3", 10.0, reference="n0")
    b = solve_unknown_resistor(netlist_flipped, "resistor3", 10.0, reference="n0")
    assert a == pytest.approx(b)
    assert a == pytest.approx(2.5)


def test_multiple_unknown_resistors_is_rejected():
    netlist = Netlist([
        V("source_v1", "n0", "n1", 10.0),
        R("resistor1", "n1", "n2"),
        R("resistor2", "n2", "n0"),
    ])
    with pytest.raises(SolverError, match="birden fazla"):
        solve_unknown_resistor(netlist, "resistor1", 5.0, reference="n0")


def test_unsupported_element_kind_is_rejected():
    netlist = Netlist([
        V("source_v1", "n0", "n1", 10.0),
        Element("source_i1", "current_source", ("n1", "n0"), 2.0),
        R("resistor1", "n1", "n0"),
    ])
    with pytest.raises(SolverError, match="desteklemiyor"):
        solve_unknown_resistor(netlist, "resistor1", 5.0, reference="n0")


def test_target_must_be_a_valueless_resistor():
    netlist = Netlist([V("source_v1", "n0", "n1", 10.0), R("resistor1", "n1", "n0", 5.0)])
    with pytest.raises(SolverError):
        solve_unknown_resistor(netlist, "resistor1", 5.0, reference="n0")
    with pytest.raises(SolverError):
        solve_unknown_resistor(netlist, "source_v1", 5.0, reference="n0")
