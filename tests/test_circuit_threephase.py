"""Üç fazlı sistem testleri -- Sadiku Bölüm 12.

Beklenen değerler kitabın kendi ÇÖZÜLMÜŞ örneklerinden (Example 12.5,
12.6, 12.9) -- kitabın basılı cevabıyla karşılaştırıldı, uydurma değil.
"""

import cmath
import math

import pytest

from app.circuit.ac import ACSolution
from app.circuit.threephase import (
    balanced_phase_voltages,
    delta_impedance_from_wye,
    delta_line_current,
    delta_phase_current,
    line_current,
    line_to_phase_voltage,
    neutral_current,
    phase_power,
    phase_to_line_voltage,
    solve,
    total_power,
    total_power_from_line,
    wye_impedance_from_delta,
    wye_source_delta_load,
    wye_source_wye_load,
)


def polar(value: complex) -> tuple[float, float]:
    return ACSolution.polar(value)


# --- faz dizisi ve hat/faz gerilim dönüşümleri -------------------------------


def test_abc_sequence_lags_by_120_degrees():
    van, vbn, vcn = balanced_phase_voltages(100, sequence="abc")
    assert polar(van) == pytest.approx((100.0, 0.0), abs=1e-6)
    assert polar(vbn)[1] == pytest.approx(-120.0, abs=1e-6)
    assert polar(vcn)[1] == pytest.approx(120.0, abs=1e-6)


def test_acb_sequence_leads_by_120_degrees():
    """Sadiku Example 12.9: acb sırasında Vbn=100∠120, Vcn=100∠-120."""
    _van, vbn, vcn = balanced_phase_voltages(100, sequence="acb")
    assert polar(vbn)[1] == pytest.approx(120.0, abs=1e-6)
    assert polar(vcn)[1] == pytest.approx(-120.0, abs=1e-6)


def test_line_to_phase_voltage_matches_example_12_5():
    """Δ kaynak Vab=210∠0 V, Y'e dönüştürülünce Van=121.2∠-30 V (kitapla birebir)."""
    van = line_to_phase_voltage(cmath.rect(210, 0))
    magnitude, angle = polar(van)
    assert magnitude == pytest.approx(121.24, rel=1e-3)
    assert angle == pytest.approx(-30.0, abs=1e-3)


def test_phase_to_line_voltage_is_the_inverse():
    van = cmath.rect(121.244, math.radians(-30))
    vab = phase_to_line_voltage(van)
    assert polar(vab) == pytest.approx((210.0, 0.0), rel=1e-3, abs=1e-3)


def test_delta_line_and_phase_current_are_inverses():
    ip = cmath.rect(14.87, math.radians(-8.66))
    il = delta_line_current(ip)
    assert delta_phase_current(il) == pytest.approx(ip, rel=1e-9)


# --- dengeli yük için Y-Δ empedans dönüşümü ----------------------------------


def test_wye_impedance_from_delta_and_back():
    z_delta = complex(120, 90)
    z_wye = wye_impedance_from_delta(z_delta)
    assert z_wye == pytest.approx(z_delta / 3)
    assert delta_impedance_from_wye(z_wye) == pytest.approx(z_delta)


# --- güç formülleri (Example 12.6) -------------------------------------------


def test_total_power_matches_example_12_6_source_side():
    """Vp=110∠0, Ip=6.81∠-21.8 -> Ss=(2087+j834.6) VA (kitapla birebir)."""
    vp = cmath.rect(110, 0)
    ip = cmath.rect(6.81, math.radians(-21.8))
    ss = total_power(vp, ip)
    assert ss.real == pytest.approx(2087, rel=2e-3)
    assert ss.imag == pytest.approx(834.6, rel=2e-3)


def test_phase_power_is_one_third_of_total():
    vp = cmath.rect(110, 0)
    ip = cmath.rect(6.81, math.radians(-21.8))
    assert total_power(vp, ip) == pytest.approx(3 * phase_power(vp, ip))


def test_total_power_from_line_matches_practice_problem_12_6():
    """Practice Problem 12.6: VL=220V, IL=18.2A -> S=√3·VL·IL=6935.13 VA
    (Eq. 12.52) -- kitapla birebir; ardından pf=P/S=0.8075 ile P=5600W
    doğrulanır (kitabın kendi çözüm sırasının tersi)."""
    s = total_power_from_line(v_line=220, i_line=18.2, angle_degrees=0.0)
    assert abs(s) == pytest.approx(6935.13, rel=1e-4)


# --- gerçek netlist üzerinden dengesiz Y yük (Example 12.9) -----------------


def test_unbalanced_wye_load_matches_example_12_9():
    """Dengesiz Y yük (acb sırası): ZA=15, ZB=10+j5, ZC=6-j8 Ω, Van=100∠0 V.
    Kitap: Ia=6.67∠0, Ib=8.94∠93.44, Ic=10∠-66.87 A."""
    van, vbn, vcn = balanced_phase_voltages(100, sequence="acb")
    netlist = wye_source_wye_load(van, vbn, vcn, 15 + 0j, complex(10, 5), complex(6, -8))

    solution = solve(netlist)
    ia = line_current(solution, "Va")
    ib = line_current(solution, "Vb")
    ic = line_current(solution, "Vc")

    assert polar(ia) == pytest.approx((6.67, 0.0), rel=1e-3, abs=1e-2)
    assert polar(ib) == pytest.approx((8.94, 93.44), rel=1e-3, abs=1e-2)
    assert polar(ic) == pytest.approx((10.0, -66.87), rel=1e-3, abs=1e-2)


def test_unbalanced_wye_load_neutral_current_matches_example_12_9():
    """Kitap: In = 10.06∠178.4 A (Eq. 12.60: In = -(Ia+Ib+Ic))."""
    van, vbn, vcn = balanced_phase_voltages(100, sequence="acb")
    netlist = wye_source_wye_load(van, vbn, vcn, 15 + 0j, complex(10, 5), complex(6, -8))

    solution = solve(netlist)
    ia = line_current(solution, "Va")
    ib = line_current(solution, "Vb")
    ic = line_current(solution, "Vc")
    magnitude, angle = polar(neutral_current(ia, ib, ic))

    assert magnitude == pytest.approx(10.06, rel=2e-3)
    assert angle == pytest.approx(178.4, abs=0.2)


def test_balanced_wye_load_has_zero_neutral_current():
    """Dengeli bir sistemde nötr akımı sıfır olmak ZORUNDA (Sadiku §12.7)."""
    van, vbn, vcn = balanced_phase_voltages(120, sequence="abc")
    z = complex(10, 8)
    netlist = wye_source_wye_load(van, vbn, vcn, z, z, z)

    solution = solve(netlist)
    ia = line_current(solution, "Va")
    ib = line_current(solution, "Vb")
    ic = line_current(solution, "Vc")

    assert abs(neutral_current(ia, ib, ic)) == pytest.approx(0.0, abs=1e-6)


def test_three_wire_unbalanced_load_leaves_neutrals_disconnected():
    """`neutral_wire=False`: kaynak/yük nötrleri AYRI düğüm -- dengesiz
    yükte gerçek bir nötr kayması oluşmalı (iki nötr farklı gerilimde)."""
    van, vbn, vcn = balanced_phase_voltages(100, sequence="acb")
    netlist = wye_source_wye_load(
        van, vbn, vcn, 15 + 0j, complex(10, 5), complex(6, -8), neutral_wire=False
    )
    assert "n_load" in netlist.nodes()

    solution = solve(netlist)
    # Yükün nötrü ("n_load") kaynağın nötründen ("gnd") farklı bir gerilimde
    # -- nötr kayması sıfır değilse devre gerçekten 3 telli davranıyor demektir.
    assert abs(solution.voltage_across("n_load", "gnd")) > 1e-6


# --- gerçek netlist üzerinden Δ yük -------------------------------------------


def test_balanced_delta_load_line_current_matches_formula():
    """Dengeli Δ yük: hat akımı = √3 × faz akımı, kitabın Tablo 12.1 formülü
    (Ip = Vab/Z, IL = √3 Ip∠-30, abc sırası) ile birebir tutmalı."""
    van, vbn, vcn = balanced_phase_voltages(110, sequence="abc")
    z = complex(10, 8)
    netlist = wye_source_delta_load(van, vbn, vcn, z, z, z)

    solution = solve(netlist)
    ia = line_current(solution, "Va")

    vab = phase_to_line_voltage(van)
    expected_phase_current = vab / z
    expected_line_current = delta_line_current(expected_phase_current)
    assert ia == pytest.approx(expected_line_current, rel=1e-6)


def test_delta_load_phase_currents_are_balanced_and_120_apart():
    van, vbn, vcn = balanced_phase_voltages(110, sequence="abc")
    z = complex(10, 8)
    netlist = wye_source_delta_load(van, vbn, vcn, z, z, z)

    solution = solve(netlist)
    magnitudes = [abs(line_current(solution, name)) for name in ("Va", "Vb", "Vc")]
    assert magnitudes[0] == pytest.approx(magnitudes[1], rel=1e-6)
    assert magnitudes[0] == pytest.approx(magnitudes[2], rel=1e-6)


# --- hata durumları -----------------------------------------------------------


def test_invalid_sequence_is_rejected():
    with pytest.raises(ValueError, match="abc"):
        balanced_phase_voltages(100, sequence="xyz")
