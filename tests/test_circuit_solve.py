import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError, solve_dc, verify_answer


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


# --- verify_answer ---------------------------------------------------------


def test_verify_accepts_textbook_rounding():
    assert verify_answer(2.4013, 2.4) is True


def test_verify_rejects_clearly_different_value():
    assert verify_answer(6.8, 10.0) is False


def test_verify_handles_zero_expected():
    assert verify_answer(0.001, 0.0) is True
    assert verify_answer(5.0, 0.0) is False


# --- cozucu ----------------------------------------------------------------


def test_requires_ground_node():
    net = Netlist([V("s", "a", "b", 10), R("1", "a", "b", 5)])
    with pytest.raises(SolverError, match="toprak"):
        solve_dc(net)


def test_requires_a_source():
    net = Netlist([R("1", "a", "gnd", 5), R("2", "a", "gnd", 5)])
    with pytest.raises(SolverError, match="kaynak yok"):
        solve_dc(net)


def test_rejects_element_without_value():
    net = Netlist([V("s", "a", "gnd", 10), Element("R1", "resistor", ("a", "gnd"))])
    with pytest.raises(SolverError, match="değer verilmemiş"):
        solve_dc(net)


def test_rejects_zero_valued_resistor():
    """GERCEK VERIDE YAKALANDI (Fiore Figure 2.23): OCR '6 Ω'yi '0' olarak
    yanlış okudu, eskiden bu deger sessizce kabul edilip element_results'ta
    ZeroDivisionError ile programı çökertiyordu (bkz. app/vision/vlm_read.py
    parse_ocr_value_hint'teki aynı olayla ilgili yorum)."""
    net = Netlist([V("s", "a", "gnd", 10), R("1", "a", "gnd", 0)])
    with pytest.raises(SolverError, match="direnç değeri 0"):
        solve_dc(net)


def test_simple_series_divider():
    """10 V, iki esit direnc -> orta nokta 5 V, akim 1 A."""
    net = Netlist([V("s", "vs", "gnd", 10), R("1", "vs", "mid", 5), R("2", "mid", "gnd", 5)])
    sol = solve_dc(net)
    assert sol.node_voltages["mid"] == pytest.approx(5.0, rel=1e-3)
    assert sol.source_currents["s"] == pytest.approx(1.0, rel=1e-3)


def test_voltage_across_uses_ground_as_zero():
    net = Netlist([V("s", "vs", "gnd", 10), R("1", "vs", "mid", 5), R("2", "mid", "gnd", 5)])
    sol = solve_dc(net)
    assert sol.voltage_across("mid", "gnd") == pytest.approx(5.0, rel=1e-3)


def test_verified_real_circuit_matches_known_answer():
    """Oturumdaki gercek vaka: dogrulanmis topoloji, 24 V -> 2.4 A / 10 ohm."""
    net = Netlist(
        [
            V("s", "vs", "gnd", 24),
            R("6", "vs", "n1", 4),
            R("1", "n1", "gnd", 12),
            R("2", "n1", "n2", 8),
            R("3", "n2", "gnd", 12),
            R("4", "n2", "n3", 4),
            R("5", "n3", "gnd", 2),
        ]
    )
    sol = solve_dc(net)
    current = sol.source_currents["s"]
    assert verify_answer(current, 2.4)
    assert verify_answer(24 / current, 10.0)


def test_solves_bridge_that_series_parallel_cannot_reduce():
    """Asil kazanc: topology.py'nin indirgeyemedigi kopru devresi cozulebiliyor.

    Dengeli Wheatstone koprusu (tum kollar esit) -> kopru kolundan akim
    gecmez, toplam direnc R'ye esittir; 10 V'ta 10 A.
    """
    net = Netlist(
        [
            V("s", "a", "gnd", 10),
            R("1", "a", "b", 1),
            R("2", "a", "c", 1),
            R("3", "b", "gnd", 1),
            R("4", "c", "gnd", 1),
            R("5", "b", "c", 1),  # kopru kolu
        ]
    )
    sol = solve_dc(net)
    # Denge sartinda b ve c ayni gerilimde olmali
    assert sol.node_voltages["b"] == pytest.approx(sol.node_voltages["c"], abs=1e-6)
    assert sol.source_currents["s"] == pytest.approx(10.0, rel=1e-3)


def test_capacitor_is_open_circuit_in_dc():
    net = Netlist(
        [
            V("s", "vs", "gnd", 10),
            R("1", "vs", "mid", 5),
            R("2", "mid", "gnd", 5),
            Element("C1", "capacitor", ("mid", "gnd"), 1e-6),
        ]
    )
    sol = solve_dc(net)
    assert sol.node_voltages["mid"] == pytest.approx(5.0, rel=1e-3)


def test_uppercase_node_names_are_looked_up_case_insensitively():
    """ngspice düğüm adlarını sessizce küçük harfe çeviriyor -- büyük harfli
    bir düğüm adı ("A" gibi) sorgulanınca `node_voltages`'ta bulunamayıp
    KeyError veriyordu. `app/circuit/ac.py`/`threephase.py` için bu daha önce
    düzeltilmişti (bkz. `test_circuit_ac.py`'deki eşdeğer test) ama DC
    çözücüde aynı düzeltme eksikti -- gerçek veride yakalandı: VLM ile
    okunan devrelerde düğümler büyük harfle etiketleniyor (bkz.
    `app/vision/vlm_read.py`), Streamlit ekranında "A" düğümlü bir devre
    çözülünce bu hatayla patladı. `_v()`/`voltage_across()` artık sorguyu
    da küçük harfe çevirdiği için büyük harfli adlar da çalışır."""
    net = Netlist([V("s", "A", "gnd", 12.0), R("1", "A", "gnd", 10.0)])
    sol = solve_dc(net)
    assert sol.voltage_across("A", "gnd") == pytest.approx(12.0)
    assert sol.voltage_across("a", "gnd") == pytest.approx(12.0)
    assert sol.node_voltages["a"] == pytest.approx(12.0)
