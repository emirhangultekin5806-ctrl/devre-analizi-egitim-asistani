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


def V(name, plus, minus, value, phase=0.0):
    return Element(name, "voltage_source", (plus, minus), value, phase=phase)


def Z(name, a, b, magnitude, phase_degrees):
    return Element(f"Z{name}", "impedance", (a, b), magnitude, phase=phase_degrees)


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


def test_impedance_kind_uses_own_magnitude_and_phase():
    """Sadiku'nun "Z = 8+j6 Ω" kutusu -- value=BÜYÜKLÜK, phase=EMPEDANSIN
    KENDİ açısı (kaynak fazı değil, bkz. netlist.py ELEMENT_KINDS yorumu).
    frequency parametresi GÖRMEZDEN GELİNMELİ -- R/L/C'nin aksine bu tür
    zaten kendi sabit empedansını taşıyor."""
    z = impedance("impedance", 10.0, frequency=1e6, phase_degrees=36.8699)
    assert z.real == pytest.approx(8.0, rel=1e-3)
    assert z.imag == pytest.approx(6.0, rel=1e-3)
    # frekanstan bagimsiz -- ayni deger farkli frekansta da AYNI cikmali
    assert impedance("impedance", 10.0, frequency=1.0, phase_degrees=36.8699) == z


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


def test_impedance_box_solves_like_manual_rectangular_form():
    """Sadiku'da cok sik gorulen "Z = 8+j6 Ω" kutusu -- R+jX'i elle iki ayri
    eleman (direnc + bobin) olarak kurup COZUP, TEK bir 'impedance' elemani
    olarak kurulan AYNI devreyle birebir eslesmesi beklenir. El hesabi:
    |Z|=10, faz=36.8699°, I = 10V/10Ω∠36.8699° = 1∠-36.8699° A."""
    frequency = 1e3
    omega = 2 * math.pi * frequency
    net_manual = Netlist(
        [V("s", "a", "gnd", 10.0), R("1", "a", "b", 8.0), L("1", "b", "gnd", 6.0 / omega)]
    )
    net_impedance = Netlist([V("s", "a", "gnd", 10.0), Z("1", "a", "gnd", 10.0, 36.8699)])

    sol_manual = solve_ac(net_manual, frequency)
    sol_impedance = solve_ac(net_impedance, frequency)

    i_manual = sol_manual.source_currents["s"]
    i_impedance = sol_impedance.source_currents["s"]
    assert abs(i_manual - i_impedance) < 1e-6
    magnitude, angle = ACSolution.polar(i_impedance)
    assert magnitude == pytest.approx(1.0, rel=1e-3)
    assert angle == pytest.approx(-36.8699, abs=0.1)


def test_rejects_zero_valued_impedance():
    net = Netlist([V("s", "a", "gnd", 10.0), Z("1", "a", "gnd", 0.0, 30.0)])
    with pytest.raises(SolverError, match="impedance değeri 0"):
        solve_ac(net, 1e3)


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


def test_rejects_zero_valued_resistor():
    """bkz. solve.py'deki ayni testin yorumu -- 0 Ω, empedans hesabinda
    (element_results_ac -> impedance) sifira bolmeye yol acar."""
    net = Netlist([V("s", "a", "gnd", 10.0), R("1", "a", "gnd", 0.0)])
    with pytest.raises(SolverError, match="direnç değeri 0"):
        solve_ac(net, 1e3)


def test_rejects_zero_valued_capacitor():
    """BULUNDU (2026-08-21 denetimi, gercek cagriyla dogrulandi): 0Ω direnc
    icin var olan koruma kapasitore hic uygulanmiyordu -- solve_ac 0F'lik
    bir kapasitoru SESSIZCE kabul ediyordu (ngspice hata vermiyor), cozum
    "basarili" gorunuyordu, ama element_results_ac->impedance()'daki
    1/(jωC) hesabi C=0 ile ZeroDivisionError ile COKUYORDU -- kullanici
    "cozuldu" saniyordu, sonuc adiminda program cokuyordu."""
    net = Netlist([V("s", "a", "gnd", 10.0), C("1", "a", "gnd", 0.0)])
    with pytest.raises(SolverError, match="capacitor değeri 0"):
        solve_ac(net, 1e3)


def test_rejects_zero_valued_inductor():
    """Bobinde (jωL) bolme YOK -- ZeroDivisionError riski tasimiyor -- ama
    0H fiziksel olarak ayni sekilde anlamsiz (okuma hatasi), tutarlilik
    icin o da reddedilir."""
    net = Netlist([V("s", "a", "gnd", 10.0), L("1", "a", "gnd", 0.0)])
    with pytest.raises(SolverError, match="inductor değeri 0"):
        solve_ac(net, 1e3)


def test_uppercase_node_names_are_looked_up_case_insensitively():
    """ngspice düğüm adlarını sessizce küçük harfe çeviriyor -- büyük
    harfli bir düğüm adı ("N" gibi) sorgulanınca `node_voltages`'ta
    bulunamayıp KeyError veriyordu (gerçek veride yakalandı, bkz.
    `app/circuit/threephase.py` geçmişi). `_v()`/`voltage_across()` artık
    sorguyu da küçük harfe çevirdiği için büyük harfli adlar da çalışır."""
    net = Netlist([V("s", "N", "gnd", 1.0), R("1", "N", "gnd", 10.0)])
    solution = solve_ac(net, 1e3)
    assert solution.voltage_across("N", "gnd") == pytest.approx(1 + 0j)
    assert solution.voltage_across("n", "gnd") == pytest.approx(1 + 0j)


def test_describe_node_uses_polar_notation():
    net = Netlist([V("s", "n1", "gnd", 1.0), R("1", "n1", "out", 1000.0), C("1", "out", "gnd", 159.155e-9)])
    text = solve_ac(net, 1e3).describe_node("out")
    assert "∠" in text and "°" in text


def test_polar_conversion():
    magnitude, angle = ACSolution.polar(complex(0, 1))
    assert magnitude == pytest.approx(1.0)
    assert angle == pytest.approx(90.0)
    assert ACSolution.polar(cmath.rect(5, math.radians(30)))[1] == pytest.approx(30.0)


# --- faz kaydırmalı kaynaklar ------------------------------------------------
#
# PySpice'ın SinusoidalVoltageSource/SinusoidalCurrentSource sarmalayıcıları
# AC faz parametresini desteklemiyor (yalnızca genlik) — bu yüzden faz≠0
# olduğunda ham SPICE satırı ("DC 0 AC genlik faz") kullanılıyor
# (bkz. `app/circuit/ac.py` `_add_phased_source`). Faz=0 durumu (varsayılan)
# değişmedi, mevcut testler onu zaten kapsıyor.


def test_a_phased_source_reproduces_its_own_phase_on_a_resistive_load():
    """Saf dirençli yükte faz kayması olmaz: çıkış, kaynağın fazının aynısı olmalı."""
    net = Netlist([V("s", "n1", "gnd", 10.0, phase=30.0), R("1", "n1", "gnd", 1000.0)])
    magnitude, angle = ACSolution.polar(solve_ac(net, 1e3).node_voltages["n1"])
    assert magnitude == pytest.approx(10.0, rel=1e-6)
    assert angle == pytest.approx(30.0, abs=1e-3)


def test_series_phased_sources_add_as_phasors():
    """İki faz kaydırmalı kaynak seri bağlıyken toplam gerilim FAZÖR toplamı olmalı.

    V1=10∠0°, V2=10∠90° seri: toplam = 10+j10 = 14.142∠45° (temel fazör
    cebiri — Sadiku Bölüm 9). Faz yanlış uygulansaydı bu toplam tutmazdı.
    """
    net = Netlist(
        [
            V("1", "n1", "gnd", 10.0, phase=0.0),
            V("2", "n2", "n1", 10.0, phase=90.0),
            R("load", "n2", "gnd", 1000.0),
        ]
    )
    expected = cmath.rect(10.0, 0.0) + cmath.rect(10.0, math.radians(90.0))
    magnitude, angle = ACSolution.polar(solve_ac(net, 1e3).node_voltages["n2"])
    assert magnitude == pytest.approx(abs(expected), rel=1e-6)
    assert angle == pytest.approx(cmath.phase(expected) * 180 / cmath.pi, abs=1e-3)


def test_default_phase_is_zero_and_unaffected():
    """Faz belirtilmeyen (varsayılan) kaynaklar eskisi gibi 0° davranmalı —
    yeni alanın geriye dönük uyumluluğu."""
    net = Netlist([V("s", "n1", "gnd", 5.0), R("1", "n1", "gnd", 500.0)])
    _, angle = ACSolution.polar(solve_ac(net, 1e3).node_voltages["n1"])
    assert angle == pytest.approx(0.0, abs=1e-6)
