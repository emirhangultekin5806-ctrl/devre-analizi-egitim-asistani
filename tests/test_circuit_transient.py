"""Birinci dereceden geçici rejim (RC/RL) testleri -- Sadiku Bölüm 7.

Beklenen değerler kitabın kendi ÇÖZÜLMÜŞ örneklerinden (Example 7.10,
Example 7.12) -- devre elle kurulup topoloji o örneklerin metninden
türetildi, sonuç kitabın basılı cevabıyla karşılaştırıldı.
"""

import math

import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError, power_balance
from app.circuit.transient import (
    rc_step_response,
    rl_step_response,
    series_rlc_natural_response,
    series_rlc_response,
    snapshot_at,
)


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


def C(name, a, b, value):
    return Element(name, "capacitor", (a, b), value)


def L(name, a, b, value):
    return Element(name, "inductor", (a, b), value)


# --- RC: Sadiku Example 7.10 (Figure 7.43) -----------------------------------
#
# Anahtar A'dan B'ye t=0'da geçiyor. Kitap: v(0)=15V, v(∞)=30V, τ=2s,
# v(t)=30-15e^(-0.5t)V, v(1)=20.9V, v(4)=27.97V.
_RC_BEFORE = Netlist(
    [V("Vs", "n1", "gnd", 24.0), R("R3k", "n1", "na", 3000.0), R("R5k", "na", "gnd", 5000.0), C("C", "na", "gnd", 0.5e-3)]
)
_RC_AFTER = Netlist(
    [V("Vs", "n2", "gnd", 30.0), R("R4k", "n2", "nb", 4000.0), C("C", "nb", "gnd", 0.5e-3)]
)


def test_rc_step_response_matches_example_7_10():
    response = rc_step_response(_RC_BEFORE, _RC_AFTER, "C")
    assert response.x0 == pytest.approx(15.0, rel=1e-6)
    assert response.x_inf == pytest.approx(30.0, rel=1e-6)
    assert response.tau == pytest.approx(2.0, rel=1e-6)
    assert response.at(1.0) == pytest.approx(20.9, rel=1e-3)
    assert response.at(4.0) == pytest.approx(27.97, rel=1e-3)


def test_rc_response_rejects_negative_time():
    response = rc_step_response(_RC_BEFORE, _RC_AFTER, "C")
    with pytest.raises(ValueError, match="negatif"):
        response.at(-1.0)


def test_rc_response_describe_is_student_readable():
    response = rc_step_response(_RC_BEFORE, _RC_AFTER, "C")
    text = response.describe()
    assert "v(t)" in text and "e^" in text and "τ" not in text  # sayısal τ gösteriliyor, sembol değil


# --- RL: Sadiku Example 7.12 (Figure 7.51) -----------------------------------
#
# Anahtar kapalıyken 3Ω kısa devre; t=0'da açılıyor, 3Ω devreye giriyor.
# Kitap: i(0)=5A, i(∞)=2A, τ=1/15s, i(t)=2+3e^(-15t)A.
_RL_BEFORE = Netlist([V("Vs", "n1", "gnd", 10.0), R("R2", "n1", "n2", 2.0), L("L", "n2", "gnd", 1 / 3)])
_RL_AFTER = Netlist(
    [V("Vs", "n1", "gnd", 10.0), R("R2", "n1", "n2", 2.0), R("R3", "n2", "n3", 3.0), L("L", "n3", "gnd", 1 / 3)]
)


def test_rl_step_response_matches_example_7_12():
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    assert response.x0 == pytest.approx(5.0, rel=1e-6)
    assert response.x_inf == pytest.approx(2.0, rel=1e-6)
    assert response.tau == pytest.approx(1 / 15, rel=1e-6)
    assert response.at(0.1) == pytest.approx(2 + 3 * math.exp(-1.5), rel=1e-6)


def test_rl_thevenin_resistance_matches_book():
    """Kitap: R_Th = 2 + 3 = 5 Ω (kaynak öldürülüp bobin çıkarılınca seri direnç)."""
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    # τ = L/R_Th -> R_Th = L/τ
    assert (1 / 3) / response.tau == pytest.approx(5.0, rel=1e-6)


# --- eleman bazlı anlık değerler (snapshot_at) -------------------------------


def test_snapshot_matches_analytic_inductor_voltage():
    """V_L = L di/dt = d/dt[2+3e^(-15t)]/3 = -15e^(-15t) -- kitabın kendi
    "Check: KVL must be satisfied" adımının aynısı, farklı bir yoldan."""
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    for t in (0.05, 0.2, 1.0):
        results = snapshot_at(_RL_AFTER, response, t)
        expected_v_l = -15.0 * math.exp(-15 * t)
        assert results["L"].voltage == pytest.approx(expected_v_l, rel=1e-3)


def test_snapshot_power_balances_at_every_instant():
    """Tellegen teoremi yalnızca t=0 ya da t=∞'da değil, TÜM t≥0 için
    tutmalı -- devre her anda fizik kurallarına uymak zorunda."""
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    for t in (0.0, 0.05, 0.2, 1.0, 5.0):
        results = snapshot_at(_RL_AFTER, response, t)
        assert power_balance(results) == pytest.approx(0.0, abs=1e-8)


def test_snapshot_at_infinity_matches_steady_state_current():
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    results = snapshot_at(_RL_AFTER, response, 50.0)  # τ=1/15s'ye kıyasla çok büyük
    assert results["L"].current == pytest.approx(2.0, rel=1e-6)
    assert results["L"].voltage == pytest.approx(0.0, abs=1e-6)


# --- hata durumları -----------------------------------------------------------


def test_rc_rejects_non_capacitor():
    net = Netlist([R("R1", "a", "gnd", 10.0)])
    with pytest.raises(SolverError, match="kapasitör değil"):
        rc_step_response(net, net, "R1")


def test_rc_rejects_changing_capacitance():
    before = Netlist([C("C", "a", "gnd", 1e-3), R("R1", "a", "gnd", 10.0)])
    after = Netlist([C("C", "a", "gnd", 2e-3), R("R1", "a", "gnd", 10.0)])
    with pytest.raises(SolverError, match="sığa değeri değişmemeli"):
        rc_step_response(before, after, "C")


def test_snapshot_rejects_unknown_element():
    response = rl_step_response(_RL_BEFORE, _RL_AFTER, "L")
    bad_netlist = Netlist([R("R1", "a", "gnd", 10.0)])
    with pytest.raises(KeyError):
        snapshot_at(bad_netlist, response, 1.0)


# --- 2. derece: Sadiku Example 8.3 + 8.4 (seri RLC) --------------------------
#
# Example 8.3: R=40Ω, L=4H, C=1/4F -> α=5, ω0=1, s1=-0.101, s2=-9.899
# (aşırı sönümlü). Example 8.4: R=9Ω, L=0.5H, C=0.02F, i(0)=1A, v(0)=-6V
# -> α=9, ω0=10, az sönümlü, i(t)=e^-9t(cos4.359t+0.6882sin4.359t) A.


def test_series_rlc_classification_matches_example_8_3():
    response = series_rlc_response(40.0, 4.0, 0.25, i0=0.0, di0=0.0)
    assert response.damping == "overdamped"
    assert response.alpha == pytest.approx(5.0, rel=1e-6)
    assert response.omega0 == pytest.approx(1.0, rel=1e-6)
    assert response.s1 == pytest.approx(-0.101, abs=1e-3)
    assert response.s2 == pytest.approx(-9.899, abs=1e-3)


def test_series_rlc_underdamped_matches_example_8_4():
    # di(0)/dt = -[R*i(0)+v(0)]/L = -[9*1+(-6)]/0.5 = -6 A/s (Sadiku Eq. 8.4.3)
    response = series_rlc_response(9.0, 0.5, 0.02, i0=1.0, di0=-6.0)
    assert response.damping == "underdamped"
    assert response.omega_d == pytest.approx(4.359, abs=1e-3)
    assert response.a1 == pytest.approx(1.0, rel=1e-6)
    assert response.a2 == pytest.approx(0.6882, abs=1e-4)
    assert response.at(0.0) == pytest.approx(1.0, rel=1e-6)


def test_series_rlc_critically_damped_boundary():
    """α=ω0 sınır durumu: R=2√(L/C) -- kitabın kendi tanımı (§8.3)."""
    l_value, c_value = 1.0, 0.25
    omega0 = 1 / math.sqrt(l_value * c_value)
    r_critical = 2 * l_value * omega0  # alpha = R/(2L) = omega0
    response = series_rlc_response(r_critical, l_value, c_value, i0=2.0, di0=0.0)
    assert response.damping == "critically_damped"
    assert response.alpha == pytest.approx(response.omega0, rel=1e-9)
    assert response.at(0.0) == pytest.approx(2.0, rel=1e-6)


def test_second_order_response_rejects_negative_time():
    response = series_rlc_response(9.0, 0.5, 0.02, i0=1.0, di0=-6.0)
    with pytest.raises(ValueError, match="negatif"):
        response.at(-0.1)


# --- 2. derece: gerçek netlist'ten otomatik türetim --------------------------
#
# `series_rlc_natural_response`, i(0)/v(0)'ı "before" devresinden
# (süreklilik), di(0)/dt'yi "after" devresinde L/C'yi anlık değerlerine
# sabitleyip KVL uygulayarak, R'yi de Thevenin direnciyle OTOMATİK türetir.
# Doğrulama: elle hesaplanan (R,L,C,i0,di0) ile `series_rlc_response`'a
# verilenle BİREBİR aynı sonucu üretmeli -- bu, otomatik türetimin doğru
# çalıştığının kanıtı (Example 8.4'ün kendi sayılarıyla kurulmuş devre).

_RLC_BEFORE = Netlist(
    [
        # L üzerinden 1A, C üzerinde -6V kuran basit yardımcı devre.
        Element("V1", "voltage_source", ("n1", "gnd"), 9.0),
        R("Rx", "n1", "n2", 9.0),
        L("L", "n2", "gnd", 0.5),
        Element("V2", "voltage_source", ("n3", "gnd"), -6.0),
        C("C", "n3", "gnd", 0.02),
    ]
)
_RLC_AFTER = Netlist(
    [
        R("R", "gnd", "na", 9.0),
        L("L", "na", "nb", 0.5),
        C("C", "nb", "gnd", 0.02),
    ]
)


def test_series_rlc_natural_response_matches_manual_calculation():
    auto = series_rlc_natural_response(_RLC_BEFORE, _RLC_AFTER, "L", "C")
    manual = series_rlc_response(9.0, 0.5, 0.02, i0=1.0, di0=-6.0)
    assert auto.damping == manual.damping == "underdamped"
    assert auto.alpha == pytest.approx(manual.alpha, rel=1e-6)
    assert auto.omega_d == pytest.approx(manual.omega_d, rel=1e-6)
    assert auto.a1 == pytest.approx(manual.a1, rel=1e-6)
    assert auto.a2 == pytest.approx(manual.a2, rel=1e-6)
    for t in (0.0, 0.1, 0.3, 1.0):
        assert auto.at(t) == pytest.approx(manual.at(t), rel=1e-4)


def test_series_rlc_natural_response_requires_adjacent_l_and_c():
    """L ve C bir düğümü paylaşmıyorsa (basit seri döngü değilse) açık
    hata verilmeli -- sessizce yanlış R_th hesaplanmamalı."""
    after = Netlist(
        [
            R("R1", "gnd", "na", 9.0),
            L("L", "na", "nx", 0.5),
            R("Rmid", "nx", "ny", 1.0),  # L ile C arasına giren üçüncü düğüm
            C("C", "ny", "gnd", 0.02),
        ]
    )
    with pytest.raises(SolverError, match="paylaşmıyor"):
        series_rlc_natural_response(_RLC_BEFORE, after, "L", "C")
