"""'📷 Kendi Devreni Yükle' ekranının Streamlit'in resmi `AppTest` çerçevesiyle
(tarayıcısız) uçtan uca testi — elle giriş yolu (VLM gerektirmez).

Bu test, geliştirme sırasında GERÇEK bir hatayı yakaladı: `solve_dc`
büyük harfli düğüm adlarında ("A" gibi) `KeyError` veriyordu çünkü ngspice
düğüm adlarını sessizce küçük harfe çeviriyor ve `Solution._v()` sorguyu
küçük harfe çevirmiyordu — aynı hata sınıfı `solve_ac`/`threephase.py` için
daha önce düzeltilmişti (bkz. `test_circuit_solve.py::
test_uppercase_node_names_are_looked_up_case_insensitively`), DC tarafında
eksikti. VLM ile okunan düğümler büyük harfle etiketlendiği için
(`app/vision/vlm_read.py`) bu ekran olmasaydı hata görünmeyebilirdi.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app" / "ui" / "streamlit_app.py"


def _select_screen_and_go_manual() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("📷 Kendi Devreni Yükle")
    at.run()
    manual_btn = next(b for b in at.button if b.label == "Elle gir")
    manual_btn.click()
    at.run()
    return at


def test_screen_shows_all_three_entry_buttons():
    """BULUNDU (2026-08-21 denetimi): ekran gercek YOLO+connectivity
    pipeline'ina hic baglanmamisti, sadece butun goruntuyu VLM'e veren eski
    yol vardi. Pipeline yolu eklendikten sonra ucu de ayni ekranda
    gorunmeli -- yanlislikla birini silip digerini unutmak (bkz. buton
    etiket degisikligiyle KIRILAN yukaridaki testler) burada yakalanir."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("📷 Kendi Devreni Yükle")
    at.run()
    assert not at.exception
    labels = {b.label for b in at.button}
    assert "🔍 Pipeline ile oku (önerilen)" in labels
    assert "VLM ile oku (deneysel)" in labels
    assert "Elle gir" in labels


def test_manual_entry_starts_with_empty_draft():
    at = _select_screen_and_go_manual()
    assert not at.exception
    assert at.session_state["own_circuit"] == {"rows": [], "frequency_hz": None}


def test_solving_a_simple_dc_circuit_matches_ohms_law():
    at = _select_screen_and_go_manual()
    at.session_state["own_circuit"]["rows"] = [
        {"name": "R1", "kind": "resistor", "value": 10.0, "node_a": "A", "node_b": "gnd", "phase_degrees": 0.0},
        {"name": "V1", "kind": "voltage_source", "value": 12.0, "node_a": "A", "node_b": "gnd", "phase_degrees": 0.0},
    ]
    at.run()
    assert not at.exception

    solve_btn = next(b for b in at.button if b.label == "Çöz")
    solve_btn.click()
    at.run()
    assert not at.exception, f"'Çöz' düğmesi hataya düştü: {at.exception}"

    results_df = at.dataframe[-1].value
    row = results_df[results_df["Eleman"] == "R1"].iloc[0]
    assert row["I (A)"] == pytest.approx(1.2)
    assert row["V (V)"] == pytest.approx(12.0)
    assert row["P (W)"] == pytest.approx(14.4)

    balance_caption = next(c.value for c in at.caption if "Güç dengesi" in c.value)
    assert "tutarlı" in balance_caption


def test_invalid_circuit_shows_error_not_crash():
    """Aynı düğüme bağlı iki uçlu (kısa devre) bir eleman -- `Netlist`
    kendi doğrulamasında reddeder, ekran çökmemeli, kullanıcıya
    `st.error` ile gösterilmeli."""
    at = _select_screen_and_go_manual()
    at.session_state["own_circuit"]["rows"] = [
        {"name": "R1", "kind": "resistor", "value": 10.0, "node_a": "A", "node_b": "A", "phase_degrees": 0.0},
    ]
    at.run()

    solve_btn = next(b for b in at.button if b.label == "Çöz")
    solve_btn.click()
    at.run()
    assert not at.exception, "Geçersiz devre ekranı çökertmemeli, st.error göstermeli"
    assert any("Devre geçersiz" in e.value for e in at.error)
