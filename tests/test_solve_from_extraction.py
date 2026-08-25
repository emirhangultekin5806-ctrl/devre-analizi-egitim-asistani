"""solve_extraction'un DC/AC dispatch'ini dogrular -- bir devrede frekans
okunmussa (VLM en az bir kaynakta "f=..." bulmussa) otomatik solve_ac'e,
yoksa solve_dc'ye gitmeli (bkz. scripts/solve_from_extraction.py).

VLM gercek cagrisi yerine crop dosyasinin ICERIGINE (bilesen adi) gore
sabit bir okuma donduren sahte fonksiyon kullanilir -- gercek Ollama'ya
bagimli olmadan degistirilen dispatch mantigini test eder.
"""
from __future__ import annotations

import base64
import cmath
import json
import sys
from pathlib import Path

import pytest

import scripts.solve_from_extraction as sfe


def _fake_reader(readings: dict[str, dict]):
    def read_component_value(image_base64: str) -> dict:
        name = base64.b64decode(image_base64).decode()
        return readings[name]

    return read_component_value


def _fake_dependent_reader(readings: dict[str, dict]):
    def read_dependent_source(image_base64: str) -> dict:
        name = base64.b64decode(image_base64).decode()
        return readings[name]

    return read_dependent_source


def _write_crop(tmp_path: Path, name: str) -> str:
    path = tmp_path / f"{name}.png"
    path.write_bytes(name.encode())
    return str(path)


def _extraction(tmp_path: Path, components: dict[str, dict]) -> dict:
    return {
        "components": {
            name: {**comp, "crop": _write_crop(tmp_path, name)} for name, comp in components.items()
        }
    }


def test_dc_circuit_dispatches_to_solve_dc(tmp_path, monkeypatch):
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 50.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)
    assert isinstance(out["power_balance"], float)
    assert abs(out["power_balance"]) < 1e-6


def test_ac_circuit_with_frequency_dispatches_to_solve_ac(tmp_path, monkeypatch):
    """Sadiku/Fiore RC alcak-geciren, kesim frekansinda -- frequency_hz
    okunmus olmasi tek basina DC yolundan AC yoluna gecirmeye yetmeli."""
    readings = {
        "source_v1": {"value": 1.0, "phase_degrees": 0, "frequency_hz": 1e3},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 159.155e-9, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)
    assert isinstance(out["power_balance"], complex)
    assert abs(out["power_balance"]) < 1e-6
    out_v = out["results"]["capacitor1"].voltage
    magnitude = abs(out_v)
    assert magnitude == pytest.approx(0.7071, rel=1e-3)


def test_ocr_value_hint_skips_vlm_call(tmp_path, monkeypatch):
    """ocr_value_hint temiz parse edilirse VLM HIC cagrilmamali (hiz kazanci
    -- bkz. app/vision/vlm_read.py parse_ocr_value_hint docstring'i)."""

    def _must_not_be_called(image_base64: str) -> dict:
        raise AssertionError("read_component_value cagrilmamaliydi, OCR hint yeterliydi")

    monkeypatch.setattr(sfe, "read_component_value", _must_not_be_called)
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0], "ocr_value_hint": "10 V"},
            "resistor1": {"kind": "resistor", "nets": [1, 0], "ocr_value_hint": "50 ohm"},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)
    assert out["elements"][0]["value"] in (10.0, 50.0)  # ikisi de OCR'dan geldi, VLM'siz


def test_ambiguous_ocr_hint_falls_back_to_vlm(tmp_path, monkeypatch):
    """ocr_value_hint yoksa (extraction.json'da hic alan olmayabilir --
    bkz. eski cikti/Fiore figurleri) normal VLM yoluna dusmeli."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 50.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},  # ocr_value_hint yok
            "resistor1": {"kind": "resistor", "nets": [1, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)
    assert abs(out["power_balance"]) < 1e-6


def test_conflicting_frequencies_raise(tmp_path, monkeypatch):
    readings = {
        "source_v1": {"value": 1.0, "phase_degrees": 0, "frequency_hz": 1e3},
        "source_v2": {"value": 1.0, "phase_degrees": 0, "frequency_hz": 2e3},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "source_v2": {"kind": "source_v", "nets": [1, 0]},
        },
    )
    with pytest.raises(sfe.SolveFromExtractionError, match="birden fazla farkli frekans"):
        sfe.solve_extraction(data, verbose=False)


# --- fazor bolgesi ("j2 Ω" gosterimi) ---------------------------------------
#
# BULUNDU (2026-08-25, Devre Fotoları 1-100/28.png): Sadiku Bolum 9-11'de
# devreler FAZOR BOLGESINDE cizilir -- bobin "j2 Ω", kondansator "-j16 Ω"
# olarak ETIKETLENIR (H/F degil). Bu ayrim yokken j2Ω -> 2 HENRY, -j16Ω ->
# 16 FARAD okunuyor, ve semada frekans yazmadigi icin devre DC saniliip
# kondansator acik / bobin kisa devre olarak SESSIZCE yanlis cozuluyordu.


def test_ohm_labelled_inductor_becomes_impedance(tmp_path, monkeypatch):
    """Birimi Ω olan bir bobin = fazor reaktansi -> `impedance` elemani
    (buyukluk = sayi, faz = +90°). Ve saf fazor devresi FREKANS ISTEMEZ."""
    readings = {
        "source_v1": {"value": 50.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "V"},
        "resistor1": {"value": 3.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
        "inductor1": {"value": 4.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "inductor1": {"kind": "inductor", "nets": [2, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)

    ind = next(e for e in out["elements"] if e["name"] == "inductor1")
    assert ind["kind"] == "impedance", "Ω birimli bobin impedance olmaliydi"
    # Seri 3+j4 -> |Z|=5, I = 50/5 = 10 A. Fazor cozumu yapildiginin kaniti.
    assert isinstance(out["power_balance"], complex)
    assert abs(out["results"]["resistor1"].current) == pytest.approx(10.0, rel=1e-3)


def test_ohm_labelled_capacitor_gets_negative_phase(tmp_path, monkeypatch):
    """Kondansator fazor bolgesinde HER ZAMAN -jX -- isaret YOLO'nun sembol
    sinifindan gelir, ayrica "j" mi "-j" mi diye okumaya gerek yok."""
    readings = {
        "source_v1": {"value": 50.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "V"},
        "resistor1": {"value": 3.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
        "capacitor1": {"value": 4.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)

    cap = next(e for e in out["elements"] if e["name"] == "capacitor1")
    assert cap["kind"] == "impedance"
    # 3-j4 -> |Z|=5, akim 10 A ama faz POZITIF (kapasitif devre akimi ilerler).
    current = out["results"]["resistor1"].current
    assert abs(current) == pytest.approx(10.0, rel=1e-3)
    assert cmath.phase(current) > 0, "kapasitif devrede akim gerilimi ONCELER"


def test_negative_reactance_reading_does_not_flip_sign(tmp_path, monkeypatch):
    """VLM "-j16 Ω" icin sayiyi -16 dondurebilir (eksi isaretini birlikte
    okur). Isaret ZATEN sembol sinifindan geliyor (kondansator -> -90°);
    negatif buyuklugu oldugu gibi birakmak isareti IKI KEZ uygulayip
    KAPASITIF elemani INDUKTIF yapar -- sessizce yanlis devre."""
    readings = {
        "source_v1": {"value": 50.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "V"},
        "resistor1": {"value": 3.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
        "capacitor1": {"value": -4.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "Ω"},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)

    cap = next(e for e in out["elements"] if e["name"] == "capacitor1")
    assert cap["value"] == 4.0, "buyukluk POZITIF olmaliydi"
    # Hala KAPASITIF: akim gerilimi onceler (faz pozitif).
    assert cmath.phase(out["results"]["resistor1"].current) > 0


def test_henry_labelled_inductor_stays_inductor(tmp_path, monkeypatch):
    """GERCEK (H cinsinden) bir bobin DOKUNULMADAN kalmali -- ve boyle bir
    devre frekans olmadan cozulememeli (frekans sonucu DEGISTIRIR, uydurmak
    YASAK)."""
    readings = {
        "source_v1": {"value": 50.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "V"},
        "inductor1": {"value": 1e-3, "phase_degrees": 0.0, "frequency_hz": None, "unit": "mH"},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "inductor1": {"kind": "inductor", "nets": [1, 0]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)

    ind = next(e for e in out["elements"] if e["name"] == "inductor1")
    assert ind["kind"] == "inductor", "H birimli bobin DEGISMEMELIYDI"
    # Frekans yok -> DC yolu (bobin kisa devre), fazor yoluna KAYMAMALI.
    assert isinstance(out["power_balance"], float)


# --- bagimli kaynak (dependent_vcvs) cozumlemesi ----------------------------
#
# GERCEK VERIDE DOGRULANDI (Fiore Figure 2.23): dependent_vcvs govdesi
# "2vo" tasiyor, resistor1'in KENDI kirpiminda ayrica "+ vo -" etiketi
# var -- control_label_hint bunu "o" olarak yakaliyor (bkz.
# devre-yolo-dedektor/extract_for_solve.py).


def _dependent_circuit(tmp_path, control_is_current: bool, extra_components: dict | None = None):
    monkeypatch_readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 5.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 3.0, "phase_degrees": 0, "frequency_hz": None},
    }
    dependent_readings = {
        "dependent_vcvs1": {"gain": 2.0, "control_symbol": "o", "control_is_current": control_is_current},
    }
    components = {
        "ground": {"kind": "ground", "nets": [0]},
        "source_v1": {"kind": "source_v", "nets": [1, 0]},
        "resistor1": {"kind": "resistor", "nets": [1, 0], "control_label_hint": "o"},
        "dependent_vcvs1": {"kind": "dependent_vcvs", "nets": [2, 0]},
        "resistor2": {"kind": "resistor", "nets": [2, 0]},
    }
    if extra_components:
        components.update(extra_components)
    data = _extraction(tmp_path, components)
    return data, monkeypatch_readings, dependent_readings


def test_dependent_vcvs_resolves_to_vcvs_with_control_nodes(tmp_path, monkeypatch):
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=False)
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))

    out = sfe.solve_extraction(data, verbose=False)

    dep_el = next(e for e in out["elements"] if e["name"] == "dependent_vcvs1")
    assert dep_el["kind"] == "vcvs"
    assert dep_el["control"] == "resistor1"
    assert abs(out["power_balance"]) < 1e-6


def test_dependent_vcvs_with_current_control_resolves_to_ccvs(tmp_path, monkeypatch):
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=True)
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))

    out = sfe.solve_extraction(data, verbose=False)

    dep_el = next(e for e in out["elements"] if e["name"] == "dependent_vcvs1")
    assert dep_el["kind"] == "ccvs"
    assert dep_el["control"] == "resistor1"
    assert abs(out["power_balance"]) < 1e-6


def test_ambiguous_control_symbol_raises(tmp_path, monkeypatch):
    """Iki eleman AYNI kontrol etiketini ('o') tasirsa hangisi oldugu
    tahmin EDILMEZ -- acikca reddedilir."""
    data, readings, dep_readings = _dependent_circuit(
        tmp_path,
        control_is_current=False,
        extra_components={"resistor2": {"kind": "resistor", "nets": [2, 0], "control_label_hint": "o"}},
    )
    readings["resistor2"] = {"value": 3.0, "phase_degrees": 0, "frequency_hz": None}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))

    with pytest.raises(sfe.SolveFromExtractionError, match="2 aday bulundu"):
        sfe.solve_extraction(data, verbose=False)


def test_missing_control_symbol_raises(tmp_path, monkeypatch):
    """Hicbir eleman dependent kaynagin istedigi sembolu tasimiyorsa
    (orn. 'z') acikca reddedilir, sessizce yanlis eslesmez."""
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=False)
    dep_readings["dependent_vcvs1"]["control_symbol"] = "z"
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))
    monkeypatch.setattr(sfe, "read_control_variable_target", lambda label, candidates: None)

    with pytest.raises(sfe.SolveFromExtractionError, match="0 aday bulundu"):
        sfe.solve_extraction(data, verbose=False)


def test_zero_ocr_matches_falls_back_to_vlm_visual_match(tmp_path, monkeypatch):
    """EasyOCR Yunanca'yi desteklemedigi icin control_label_hint boyle bir
    etiketi ("δ") asla bulamaz -- BULUNDU (2026-08-24, Devre Fotoları
    1-100/38.png). OCR'dan 0 aday geldiginde, bagimli kaynagin kirpimi
    TUM adaylarla birlikte tek bir VLM cagrisina verilip gorsel eslesme
    aranmali -- sembol metnini OKUMADAN, dogrudan hangi adayin eslestigini
    sorarak (bkz. read_control_variable_target docstring'i)."""
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=False)
    data["components"]["resistor1"].pop("control_label_hint")  # OCR bulamadi (Yunanca)
    dep_readings["dependent_vcvs1"]["control_symbol"] = "δ"
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))
    captured_labels = []

    def _fake_target(label, candidates):
        captured_labels.append(label)
        return next(
            (name for name, b64 in candidates if base64.b64decode(b64).decode() == "resistor1"), None
        )

    monkeypatch.setattr(sfe, "read_control_variable_target", _fake_target)

    out = sfe.solve_extraction(data, verbose=False)

    dep_el = next(e for e in out["elements"] if e["name"] == "dependent_vcvs1")
    assert dep_el["control"] == "resistor1"
    assert abs(out["power_balance"]) < 1e-6
    # Aranan sey SADECE alt indis olmali (i/v oneki YOK -- bkz. crop_has_label).
    assert captured_labels == ["δ"]


def test_prefixed_control_symbol_is_normalized_before_lookup(tmp_path, monkeypatch):
    """read_dependent_source bazen sadece alt indisi ("δ"), bazen tam adi
    ("i_δ") donuyor (OLCULDU, 38.png) -- aranan etiket TEK bicime
    indirgenmeli, yoksa kirpimda "iδ" yazarken "ii_δ" aranir."""
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=True)
    data["components"]["resistor1"].pop("control_label_hint")
    dep_readings["dependent_vcvs1"]["control_symbol"] = "i_δ"
    captured_labels = []

    def _fake_target(label, candidates):
        captured_labels.append(label)
        return next(
            (name for name, b64 in candidates if base64.b64decode(b64).decode() == "resistor1"), None
        )

    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))
    monkeypatch.setattr(sfe, "read_control_variable_target", _fake_target)

    sfe.solve_extraction(data, verbose=False)

    assert captured_labels == ["δ"], f"onek soyulmaliydi, gelen: {captured_labels}"


def test_vlm_fallback_also_fails_still_raises(tmp_path, monkeypatch):
    """VLM fallback da eslesme bulamazsa (gercekten yoksa) SESSIZCE tahmin
    edip yanlis bir adaya duşmek yerine acikca reddedilmeli."""
    data, readings, dep_readings = _dependent_circuit(tmp_path, control_is_current=False)
    dep_readings["dependent_vcvs1"]["control_symbol"] = "z"  # hicbir elemanda yok

    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_dependent_source", _fake_dependent_reader(dep_readings))
    monkeypatch.setattr(sfe, "read_control_variable_target", lambda label, candidates: None)

    with pytest.raises(sfe.SolveFromExtractionError, match="0 aday bulundu"):
        sfe.solve_extraction(data, verbose=False)


def test_dangling_node_with_source_is_rejected_clearly(tmp_path, monkeypatch):
    """BULUNDU (2026-08-24, Devre Fotoları 1-100/31.png, 101-131/116.png):
    connectivity bir kondansatoru devreye hic baglayamayinca (her iki ucu
    da derece-1) ngspice o dugumler icin gerilim uretmiyor, element_results
    ham `KeyError: "'n7' dugumu cozumde yok"` ile COKUYORDU -- yakalanabilir
    bir SolveFromExtractionError degil. Kaynakli devrede acik uc = cikarim
    hatasi, acikca reddedilmeli."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 50.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 20.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 0]},
            # net 2 ve 3'e BASKA hicbir eleman degmiyor -- tamamen kopuk.
            "resistor2": {"kind": "resistor", "nets": [2, 3]},
        },
    )
    with pytest.raises(sfe.SolveFromExtractionError, match="acik uc"):
        sfe.solve_extraction(data, verbose=False)


def test_sourceless_dangling_nodes_still_allowed_for_req(tmp_path, monkeypatch):
    """Acik uc kontrolu kaynaksiz (Req) yolu BOZMAMALI -- orada acik uclar
    terminallerin ta kendisi (bkz. equivalent_resistance cagrisi)."""
    readings = {
        "resistor1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 20.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "resistor1": {"kind": "resistor", "nets": [0, 1]},
            "resistor2": {"kind": "resistor", "nets": [1, 2]},
        },
    )
    out = sfe.solve_extraction(data, verbose=False)
    assert out["results"]["esdeger_direnc_ohm"] == pytest.approx(30.0)


def test_sourceless_series_circuit_computes_equivalent_resistance(tmp_path, monkeypatch):
    """'Req bul' tarzi kaynaksiz sorular GECERSIZ degil -- seri/paralel
    indirgemeyle cozulmeli (bkz. app/circuit/topology.py equivalent_resistance).
    Iki direncin ucu ucuna (n0-n1-n2) baglandigi en basit durum: acik uclar
    (n0, n2) derece-1, Req = R1 + R2."""
    readings = {
        "resistor1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 20.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "resistor1": {"kind": "resistor", "nets": [0, 1]},
            "resistor2": {"kind": "resistor", "nets": [1, 2]},
        },
    )

    out = sfe.solve_extraction(data, verbose=False)
    assert out["results"]["esdeger_direnc_ohm"] == pytest.approx(30.0)


def test_sourceless_circuit_with_shared_rail_terminal_raises(tmp_path, monkeypatch):
    """GERCEK VERIDE YAKALANDI (Sadiku Figure 2.38): acik uc bazen tek bir
    elemana degmez, ortak bir raya (3+ direncin bulustugu net) baglanir --
    derece-1 sezgisi bunu goremez. Tahmin etmek yerine acikca reddetmeli."""
    readings = {name: {"value": 1.0, "phase_degrees": 0, "frequency_hz": None} for name in ("r1", "r2", "r3")}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            # ucgen: her net (0,1,2) iki dirence deger -- derece-1 (gercek
            # acik uc) hic yok, hepsi junction.
            "r1": {"kind": "resistor", "nets": [0, 1]},
            "r2": {"kind": "resistor", "nets": [1, 2]},
            "r3": {"kind": "resistor", "nets": [2, 0]},
        },
    )

    with pytest.raises(sfe.SolveFromExtractionError, match="esdeger direnc hesaplanamadi"):
        sfe.solve_extraction(data, verbose=False)


def test_cli_main_prints_equivalent_resistance_without_crashing(tmp_path, monkeypatch, capsys):
    """BULUNDU (2026-08-21 denetimi): CLI main()'in sonuc yazdirma dongusu
    HER elemanin ElementResult (.describe() metodu olan) oldugunu varsayiyordu
    -- ama kaynaksiz (Req) yolu {"esdeger_direnc_ohm": float, "terminals": [...]}
    doner, .describe() yok, AttributeError ile CLI cokerdi. batch_solve.py
    etkilenmiyordu (o .describe() hic cagirmiyor), sadece bu CLI yolu."""
    readings = {
        "resistor1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 20.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "resistor1": {"kind": "resistor", "nets": [0, 1]},
            "resistor2": {"kind": "resistor", "nets": [1, 2]},
        },
    )
    extraction_path = tmp_path / "extraction.json"
    extraction_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["solve_from_extraction.py", "--extraction", str(extraction_path)])

    sfe.main()  # AttributeError firlatirsa test cöker -- bu yeterli kontrol

    assert "R_esdeger" in capsys.readouterr().out


def test_sourceless_circuit_rejects_zero_valued_resistor(tmp_path, monkeypatch):
    """BULUNDU (2026-08-21 denetimi, gercek cagriyla dogrulandi): solve_dc/
    solve_ac'teki 0Ω koruma bu yola (Req/Geq) HIC UGRAMIYOR -- iki 0Ω direnc
    paralel olunca equivalent_resistance -> _parallel_value'nin (r1*r2)/
    (r1+r2) hesabi 0/0 ile CRASH ediyordu. Simdi digerleriyle AYNI acik
    hatayi veriyor."""
    readings = {
        "resistor1": {"value": 0.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 20.0, "phase_degrees": 0, "frequency_hz": None},
    }
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    data = _extraction(
        tmp_path,
        {
            "resistor1": {"kind": "resistor", "nets": [0, 1]},
            "resistor2": {"kind": "resistor", "nets": [1, 2]},
        },
    )

    with pytest.raises(sfe.SolveFromExtractionError, match="direnç değeri 0"):
        sfe.solve_extraction(data, verbose=False)


def _fake_impedance_reader(readings: dict[str, dict]):
    def read_impedance(image_base64: str) -> dict:
        name = base64.b64decode(image_base64).decode()
        return readings[name]

    return read_impedance


def test_impedance_box_dispatches_to_solve_ac_via_page_text_frequency(tmp_path, monkeypatch):
    """Empedans kutusu iceren bir devre -- read_impedance frekans HIC
    okumaz (bkz. o fonksiyonun docstring'i), yani frekans SADECE sayfa
    metni yedeginden gelebilir (has_reactive artik 'impedance'i de sayiyor,
    bkz. solve_from_extraction.py'deki fix). El hesabi: V=10∠0°,
    Z=10Ω∠36.8699° (8+j6) -> I = 1∠-36.8699° A."""
    readings = {"source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None}}
    impedance_readings = {"impedance_box1": {"value": 10.0, "phase_degrees": 36.8699}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_impedance", _fake_impedance_reader(impedance_readings))

    img_path = tmp_path / "img.png"
    img_path.write_bytes(b"fake")
    (tmp_path / "img.txt").write_text("Devrede f = 1000 Hz kullanilmaktadir.", encoding="utf-8")
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "impedance_box1": {"kind": "impedance_box", "nets": [1, 0]},
        },
    )
    data["image"] = str(img_path)

    out = sfe.solve_extraction(data, verbose=False)
    assert abs(out["power_balance"]) < 1e-6
    magnitude = abs(out["results"]["impedance_box1"].current)
    assert magnitude == pytest.approx(1.0, rel=1e-3)


def _fake_switch_reader(readings: dict[str, dict]):
    def read_switch_state(image_base64: str) -> dict:
        name = base64.b64decode(image_base64).decode()
        return readings[name]

    return read_switch_state


def test_switch_dispatches_to_rc_step_response(tmp_path, monkeypatch):
    """El hesabiyla DOGRULANDI (bkz. yorum): anahtar KAPALI iken (t<0)
    R3, R2 ile PARALEL olup R2||R3=1kΩ verir -> v(0)=5V. Anahtar ACILINCA
    (t>=0) R3 devreden dusuyor (mid ucu boslukta kaliyor, akim cekmiyor)
    -> v(inf)=10*(2k/3k)=6.667V, tau=(R1||R2)*C=666.67*1e-6=6.667e-4s."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 2000.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor3": {"value": 2000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 1e-6, "phase_degrees": 0, "frequency_hz": None},
    }
    switch_readings = {"switch1": {"closed": True}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_switch_state", _fake_switch_reader(switch_readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "resistor2": {"kind": "resistor", "nets": [2, 0]},
            "resistor3": {"kind": "resistor", "nets": [4, 0]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
            "switch1": {"kind": "switch", "nets": [2, 4]},
        },
    )

    out = sfe.solve_extraction(data, verbose=False)
    response = out["results"]["gecici_yanit"]
    assert response.x0 == pytest.approx(5.0, rel=1e-6)
    assert response.x_inf == pytest.approx(6.6667, rel=1e-3)
    assert response.tau == pytest.approx(6.6667e-4, rel=1e-3)


def test_multiple_switches_rejected(tmp_path, monkeypatch):
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 1e-6, "phase_degrees": 0, "frequency_hz": None},
    }
    switch_readings = {"switch1": {"closed": True}, "switch2": {"closed": False}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_switch_state", _fake_switch_reader(switch_readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
            "switch1": {"kind": "switch", "nets": [1, 2]},
            "switch2": {"kind": "switch", "nets": [2, 0]},
        },
    )

    with pytest.raises(sfe.SolveFromExtractionError, match="2 anahtar bulundu"):
        sfe.solve_extraction(data, verbose=False)


def test_switch_with_both_capacitor_and_inductor_rejected(tmp_path, monkeypatch):
    """Ikinci derece (RLC) gecici rejim -- rc/rl_step_response TEK depolama
    elemani bekler, ikisi birden oldugunda TAHMIN etmek yerine reddedilir."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 1e-6, "phase_degrees": 0, "frequency_hz": None},
        "inductor1": {"value": 1e-3, "phase_degrees": 0, "frequency_hz": None},
    }
    switch_readings = {"switch1": {"closed": True}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_switch_state", _fake_switch_reader(switch_readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
            "inductor1": {"kind": "inductor", "nets": [2, 0]},
            # switch resistor1'e PARALEL (ayni net cifti) DEGIL -- ayri
            # bir net (3) uzerinden, yoksa kapaninca resistor1'i kisa
            # devre yapip AYRI (istenmeyen) bir hataya dusuyordu.
            "resistor2": {"kind": "resistor", "nets": [2, 3]},
            "switch1": {"kind": "switch", "nets": [3, 0]},
        },
    )

    with pytest.raises(sfe.SolveFromExtractionError, match="ikinci derece"):
        sfe.solve_extraction(data, verbose=False)


def test_cli_main_prints_transient_response_without_crashing(tmp_path, monkeypatch, capsys):
    """Req yolundaki AYNI bug sinifi burada da olabilirdi -- FirstOrderResponse
    ElementResult DEGIL, ozel bir sekil ({"gecici_yanit": ...}). CLI main()'in
    bunu .describe() ile guvenle yazdirdigini, guc dengesi kontrolune hic
    girmedigini (orada .power olmadigi icin cokerdi) dogrular."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 1e-6, "phase_degrees": 0, "frequency_hz": None},
    }
    switch_readings = {"switch1": {"closed": True}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_switch_state", _fake_switch_reader(switch_readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
            # switch resistor1'e PARALEL (ayni net cifti) DEGIL -- bkz.
            # yukaridaki test_switch_with_both_capacitor_and_inductor_rejected'daki
            # AYNI ders (kisa devreye dusmesin diye ayri net).
            "resistor2": {"kind": "resistor", "nets": [2, 3]},
            "switch1": {"kind": "switch", "nets": [3, 0]},
        },
    )
    extraction_path = tmp_path / "extraction.json"
    extraction_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["solve_from_extraction.py", "--extraction", str(extraction_path)])

    sfe.main()  # herhangi bir AttributeError firlatirsa test coker

    assert "v(t)" in capsys.readouterr().out


def test_switch_touching_ground_keeps_ground_node(tmp_path, monkeypatch):
    """BULUNDU (2026-08-24): anahtarin iki netinden biri 'gnd' ise, hangi
    net'in nets[0]/nets[1] oldugu YOLO/connectivity siralamasina bagli --
    birlestirme yonu sabit "node_b elenir" oldugu icin 'gnd' bazen SILINIP
    devrede referans dugum tumden kayboluyordu ('Devrede referans (toprak)
    dugumu yok' hatasi). 'gnd' artik HER ZAMAN hayatta kalir."""
    readings = {
        "source_v1": {"value": 10.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor1": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "resistor2": {"value": 1000.0, "phase_degrees": 0, "frequency_hz": None},
        "capacitor1": {"value": 1e-6, "phase_degrees": 0, "frequency_hz": None},
    }
    switch_readings = {"switch1": {"closed": True}}
    monkeypatch.setattr(sfe, "read_component_value", _fake_reader(readings))
    monkeypatch.setattr(sfe, "read_switch_state", _fake_switch_reader(switch_readings))
    data = _extraction(
        tmp_path,
        {
            "ground": {"kind": "ground", "nets": [0]},
            "source_v1": {"kind": "source_v", "nets": [1, 0]},
            "resistor1": {"kind": "resistor", "nets": [1, 2]},
            "capacitor1": {"kind": "capacitor", "nets": [2, 0]},
            "resistor2": {"kind": "resistor", "nets": [2, 3]},
            # anahtarin nets[1]'i (0 = gnd) -- eleme yonu SABIT olsaydi
            # (her zaman ikinci net elenir) 'gnd' silinirdi.
            "switch1": {"kind": "switch", "nets": [3, 0]},
        },
    )

    out = sfe.solve_extraction(data, verbose=False)
    assert "gecici_yanit" in out["results"]
