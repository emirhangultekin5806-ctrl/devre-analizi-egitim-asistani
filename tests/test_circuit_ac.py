"""AC (fazor) analizi testleri -- Devre Analizi 2 kapsami.

Beklenen degerler ders kitabi formullerinden geliyor (teorik), uydurma
degil: kesim frekansinda RC bolucu 0.7071/-45, seri RLC rezonansinda
I = V/R ve faz 0, empedanslar XL = 2(pi)fL / XC = 1/(2(pi)fC).
"""

import cmath
import math

import pytest

from app.circuit.ac import ACSolution, impedance, solve_ac
from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError


# Yardimcilar ad onekini kendileri koyuyor: eleman adlari benzersiz olmali,
# R("1") ile C("1") ayni ada sahip olamaz.
def R(name, a, b, value):
    return Element(f"R{name}", "resistor", (a, b), value)


def L(name, a, b, value):
    return Element(f"L{name}", "inductor", (a, b), value)


def C(name, a, b, value):
    return Element(f"C{name}", "capacitor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


# --- empedans --------------------------------------------------------------


def test_resistor_impedance_is_real():
    assert impedance("resistor", 100.0, 1e3) == complex(100, 0)


def test_inductor_impedance_matches_textbook_formula():
    """Fiore AC ornegi: 1 kHz, 50 mH -> +j314.2 ohm."""
    z = impedance("inductor", 50e-3, 1e3)
    assert z.real == pytest.approx(0.0, abs=1e-12)
    assert z.imag == pytest.approx(2 * math.pi * 1e3 * 50e-3, rel=1e-9)
    assert z.imag == pytest.approx(314.16, rel=1e-3)


def test_capacitor_impedance_matches_textbook_formula():
    """Fiore AC ornegi: 1 kHz, 750 nF -> -j212.2 ohm."""
    z = impedance("capacitor", 750e-9, 1e3)
    assert z.imag == pytest.approx(-1 / (2 * math.pi * 1e3 * 750e-9), rel=1e-9)
    assert z.imag == pytest.approx(-212.2, rel=1e-3)


def test_unknown_element_impedance_raises():
    with pytest.raises(SolverError, match="empedansı tanımlı değil"):
        impedance("voltage_source", 1.0, 1e3)


# --- fazor cozumu ----------------------------------------------------------


def test_rc_divider_at_cutoff_frequency():
    """Kesim frekansinda RC alcak geciren: 0.7071 genlik, -45 derece."""
    net = Netlist([V("s", "n1", "gnd", 1.0), R("1", "n1", "out", 1000.0), C("1", "out", "gnd", 159.155e-9)])
    solution = solve_ac(net, 1e3)
    magnitude, angle = ACSolution.polar(solution.node_voltages["out"])
    assert magnitude == pytest.approx(0.7071, rel=1e-3)
    assert angle == pytest.approx(-45.0, abs=0.1)


def test_source_amplitude_is_used_not_assumed_unity():
    """ac_magnitude verilmezse ngspice AC genligini 1 V kabul ediyordu:
    10 V'luk devrede akim 10 kat kucuk cikiyordu (gercek hata)."""
    net = Netlist([V("s", "n1", "gnd", 10.0), R("1", "n1", "gnd", 50.0)])
    solution = solve_ac(net, 1e3)
    magnitude, _ = ACSolution.polar(solution.source_currents["s"])
    assert magnitude == pytest.approx(10.0 / 50.0, rel=1e-6)


def test_series_rlc_at_resonance():
    """Rezonansta empedans salt direncdir: I = V/R, faz 0."""
    inductance, capacitance = 50e-3, 750e-9
    f0 = 1 / (2 * math.pi * math.sqrt(inductance * capacitance))
    net = Netlist(
        [
            V("s", "n1", "gnd", 10.0),
            R("1", "n1", "n2", 50.0),
            L("1", "n2", "n3", inductance),
            C("1", "n3", "gnd", capacitance),
        ]
    )
    solution = solve_ac(net, f0)
    magnitude, angle = ACSolution.polar(solution.source_currents["s"])
    assert magnitude == pytest.approx(10.0 / 50.0, rel=1e-3)
    assert angle == pytest.approx(0.0, abs=0.5)


def test_reactive_voltages_cancel_at_resonance():
    """Rezonansta V(L) ve V(C) esit buyuklukte ve zit fazda -- toplami sifir."""
    inductance, capacitance = 50e-3, 750e-9
    f0 = 1 / (2 * math.pi * math.sqrt(inductance * capacitance))
    net = Netlist(
        [
            V("s", "n1", "gnd", 10.0),
            R("1", "n1", "n2", 50.0),
            L("1", "n2", "n3", inductance),
            C("1", "n3", "gnd", capacitance),
        ]
    )
    solution = solve_ac(net, f0)
    v_l = solution.voltage_across("n2", "n3")
    v_c = solution.voltage_across("n3", "gnd")
    assert abs(v_l) == pytest.approx(abs(v_c), rel=1e-3)
    assert abs(v_l + v_c) == pytest.approx(0.0, abs=1e-6)


def test_inductor_voltage_leads_current_by_90_degrees():
    """Bobinde gerilim akimin 90 derece onunde.

    NOT: Kaynak DOGRUDAN ideal bobine baglanamaz -- DC'de bobin kisa devre
    oldugu icin cozucu tekil matris veriyor (fiziksel olarak dejenere).
    Bu yuzden seri direncli gercekci devre kullaniliyor.
    """
    net = Netlist([V("s", "n1", "gnd", 1.0), R("1", "n1", "n2", 100.0), L("1", "n2", "gnd", 10e-3)])
    solution = solve_ac(net, 1e3)
    # source_currents ZATEN kaynaktan cikan (devreden gecen) akimi veriyor;
    # ikinci kez isaret cevirmek fazi 180 derece kaydiriyordu.
    current = solution.source_currents["s"]
    v_l = solution.voltage_across("n2", "gnd")
    phase_difference = (
        ACSolution.polar(v_l)[1] - ACSolution.polar(current)[1]
    ) % 360
    assert phase_difference == pytest.approx(90.0, abs=0.5)


def test_capacitor_current_leads_voltage_by_90_degrees():
    net = Netlist([V("s", "n1", "gnd", 1.0), C("1", "n1", "gnd", 1e-6)])
    solution = solve_ac(net, 1e3)
    _, angle = ACSolution.polar(solution.source_currents["s"])
    assert angle == pytest.approx(90.0, abs=0.5)


# --- hata durumlari --------------------------------------------------------


def test_requires_ground():
    net = Netlist([V("s", "a", "b", 1.0), R("1", "a", "b", 10.0)])
    with pytest.raises(SolverError, match="toprak"):
        solve_ac(net, 1e3)


def test_requires_source():
    net = Netlist([R("1", "a", "gnd", 10.0), R("2", "a", "gnd", 10.0)])
    with pytest.raises(SolverError, match="kaynak yok"):
        solve_ac(net, 1e3)


def test_describe_node_uses_polar_notation():
    net = Netlist([V("s", "n1", "gnd", 1.0), R("1", "n1", "out", 1000.0), C("1", "out", "gnd", 159.155e-9)])
    text = solve_ac(net, 1e3).describe_node("out")
    assert "∠" in text and "°" in text


def test_polar_conversion():
    magnitude, angle = ACSolution.polar(complex(0, 1))
    assert magnitude == pytest.approx(1.0)
    assert angle == pytest.approx(90.0)
    assert ACSolution.polar(cmath.rect(5, math.radians(30)))[1] == pytest.approx(30.0)
