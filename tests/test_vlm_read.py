import pytest

import app.vision.vlm_read as vlm_read
from app.vision.vlm_read import (
    VLMReadError,
    _unit_multiplier,
    draft_to_netlist,
    parse_ocr_value_hint,
    parse_vlm_response,
    read_impedance,
)

VALID_RESPONSE = """İşte devre:
{
  "elements": [
    {"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "B"},
    {"name": "V1", "kind": "voltage_source", "value": 12, "node_plus": "A", "node_minus": "gnd", "phase_degrees": 0}
  ],
  "frequency_hz": null,
  "notlar": ""
}"""


def test_parses_valid_response_with_surrounding_prose():
    result = parse_vlm_response(VALID_RESPONSE)
    assert len(result["elements"]) == 2
    assert result["elements"][0] == {
        "name": "R1", "kind": "resistor", "value": 10.0,
        "node_a": "A", "node_b": "B", "phase_degrees": 0.0,
    }
    assert result["elements"][1]["node_a"] == "A"
    assert result["elements"][1]["node_b"] == "gnd"
    assert result["frequency_hz"] is None


def test_source_uses_node_plus_minus_not_node_a_b():
    raw = """{"elements": [
        {"name": "I1", "kind": "current_source", "value": 2, "node_plus": "X", "node_minus": "gnd"}
    ], "frequency_hz": null}"""
    result = parse_vlm_response(raw)
    assert result["elements"][0]["node_a"] == "X"
    assert result["elements"][0]["node_b"] == "gnd"


def test_reads_frequency_and_phase_for_ac():
    raw = """{"elements": [
        {"name": "V1", "kind": "voltage_source", "value": 10, "node_plus": "A", "node_minus": "gnd", "phase_degrees": 30}
    ], "frequency_hz": 60}"""
    result = parse_vlm_response(raw)
    assert result["frequency_hz"] == 60.0
    assert result["elements"][0]["phase_degrees"] == 30.0


def test_no_json_raises_with_raw_preserved():
    with pytest.raises(VLMReadError) as exc_info:
        parse_vlm_response("Üzgünüm, bu görseli okuyamadım.")
    assert exc_info.value.raw == "Üzgünüm, bu görseli okuyamadım."


def test_malformed_json_raises():
    with pytest.raises(VLMReadError):
        parse_vlm_response("{elements: [broken json}")


def test_empty_elements_list_raises():
    with pytest.raises(VLMReadError):
        parse_vlm_response('{"elements": [], "frequency_hz": null}')


def test_unknown_kind_raises_whole_response_not_dropped():
    """Bilinmeyen bir tür (örn. bağımlı kaynak) tüm yanıtı geçersiz kılar —
    tek elemanı sessizce atlayıp eksik bir devre üretmez (bkz. modül docstring'i)."""
    raw = """{"elements": [
        {"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "B"},
        {"name": "E1", "kind": "vcvs", "value": 2, "node_a": "B", "node_b": "gnd"}
    ], "frequency_hz": null}"""
    with pytest.raises(VLMReadError):
        parse_vlm_response(raw)


def test_missing_nodes_raises():
    raw = '{"elements": [{"name": "R1", "kind": "resistor", "value": 10, "node_a": "A"}], "frequency_hz": null}'
    with pytest.raises(VLMReadError):
        parse_vlm_response(raw)


def test_non_numeric_value_raises():
    raw = '{"elements": [{"name": "R1", "kind": "resistor", "value": "on ohm", "node_a": "A", "node_b": "B"}], "frequency_hz": null}'
    with pytest.raises(VLMReadError):
        parse_vlm_response(raw)


# --- _unit_multiplier ---------------------------------------------------------
#
# VLM'e biriminin AYNEN yazidaki gibi kopyalanmasi soyleniyor (bkz. modul
# docstring'i) -- sabit bir kume degil, kitapta gecen HERHANGI bir yazim
# gelebilir. Once tanimadigi birimi SESSIZCE 1.0 (carpansiz) sayiyordu --
# "MΩ" gibi tabloda olmayan bir birim, deger 1.000.000 kat kucuk okunurdu,
# hicbir hata vermeden (kod incelemesiyle bulundu, gercek veride henuz
# yakalanmadi ama mekanizma birebir op-amp/oversize hatasiyla ayni sinif:
# ust katmanda DOGRU okunan bir sey, alt katmanda SESSIZCE yanlis islenir).


def test_known_units_convert_correctly():
    assert _unit_multiplier("kohm") == 1e3
    assert _unit_multiplier("MΩ") == 1e6  # buyuk/kucuk harf -- megaohm
    assert _unit_multiplier("uF") == 1e-6
    assert _unit_multiplier(None) == 1.0
    assert _unit_multiplier("") == 1.0


def test_milliohm_and_megaohm_distinguished_by_case():
    """DENETIMDE BULUNDU (2026-08-21), kullanici miliohm'un GERCEKTEN
    kullanildigini teyit etti: eskiden "mΩ" ve "MΩ" ikisi de kucuk harfe
    cevrilip AYNI (mega, 1e6) sayiliyordu -- gercek bir miliohm degeri
    1e9 kat yanlis okunurdu. Artik buyuk/kucuk harf KORUNUYOR."""
    assert _unit_multiplier("mΩ") == 1e-3
    assert _unit_multiplier("MΩ") == 1e6
    assert _unit_multiplier("mohm") == 1e-3
    assert _unit_multiplier("Mohm") == 1e6
    # digger "m" onekleri (V/A/H) HER ZAMAN mili -- burada karisiklik yok,
    # buyuk harfli "Megavolt" gibi bir birim bu domainde hic gecmiyor.
    assert _unit_multiplier("mV") == 1e-3
    assert _unit_multiplier("mA") == 1e-3


def test_unrecognized_unit_raises_instead_of_silently_defaulting():
    with pytest.raises(ValueError, match="bilinmeyen birim"):
        _unit_multiplier("gigaohm")


# --- parse_ocr_value_hint ------------------------------------------------------
#
# GERCEK VERIDE YAKALANDI (Fiore Figure 2.23): OCR "6 Ω" yazisini tek basina
# "0" olarak okudu. Eski kod bunu GECERLI bir deger (0.0) sanip VLM'i
# atlıyordu -- cozucude ZeroDivisionError'a kadar gitti (bkz. app/circuit/
# solve.py'deki ayni olayla ilgili yorum). "0" biriMSIZ artik supheli
# sayilip VLM'e birakiliyor.


def test_bare_zero_is_rejected_falls_back_to_vlm():
    assert parse_ocr_value_hint("0") is None


def test_bare_nonzero_is_rejected_falls_back_to_vlm():
    """GERCEK VERIDE IKI AYRI ORNEKTE YAKALANDI (2026-08-21 denetimi):
    Figure 4.9 resistor5'in gercek etiketi '1 Ω' iken OCR birimsiz '10'
    okudu (10 kat yanlis); Figure 2.27 resistor1'in gercek etiketi '6 Ω'
    iken OCR birimsiz '9' okudu (yanlis rakam + kayip birim). Sadece
    birimsiz SIFIR degil, birimsiz HER sayi supheli -- birim kaybi genelde
    rakami da bozuyor, sessizce yanlis deger yerine VLM'e dusulur."""
    assert parse_ocr_value_hint("10") is None
    assert parse_ocr_value_hint("9") is None


def test_zero_with_explicit_unit_is_accepted():
    """'0 V' gibi bir kaynagin GERCEKTEN sifir olmasi fiziksel olarak
    anlamli (direncin aksine) -- birim ACIKCA yazılıysa reddedilmez."""
    result = parse_ocr_value_hint("0 V")
    assert result is not None
    assert result["value"] == 0.0


def test_clean_value_still_parses():
    result = parse_ocr_value_hint("10 kΩ")
    # `unit` de doner -- cagiran taraf "bobin ama birimi Ω" (fazor reaktansi)
    # ayrimini yapabilsin diye (bkz. is_ohm_unit).
    assert result == {"value": 10000.0, "phase_degrees": 0.0, "frequency_hz": None, "unit": "kΩ"}


# --- fazor bolgesi ayrimi (is_ohm_unit) --------------------------------------
# BULUNDU (2026-08-25, Devre Fotoları 1-100/28.png): "j2 Ω" 2 HENRY, "-j16 Ω"
# 16 FARAD olarak okunuyordu -- devre DC saniliip sessizce tamamen yanlis
# cozulecekti. Bir bobinin/kondansatorun birimi Ω ise deger REAKTANStir.


@pytest.mark.parametrize("unit", ["Ω", "ohm", "kΩ", "kohm", "MΩ", "mΩ", " Ω "])
def test_is_ohm_unit_true(unit):
    assert vlm_read.is_ohm_unit(unit) is True


@pytest.mark.parametrize("unit", [None, "", "H", "mH", "F", "uF", "V", "A", "Hz"])
def test_is_ohm_unit_false(unit):
    assert vlm_read.is_ohm_unit(unit) is False


# --- draft_to_netlist --------------------------------------------------------


def test_draft_to_netlist_builds_valid_netlist():
    rows = [
        {"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "B", "phase_degrees": 0},
        {"name": "V1", "kind": "voltage_source", "value": 12, "node_a": "A", "node_b": "gnd", "phase_degrees": 0},
    ]
    netlist = draft_to_netlist(rows)
    assert len(netlist) == 2
    assert netlist.by_name("R1").nodes == ("A", "B")


def test_draft_to_netlist_rejects_same_node_short_circuit():
    """Element'in kendi doğrulaması burada devreye girer (kullanıcı düzeltmeden
    onaylarsa bile kısa devre sessizce kabul edilmez)."""
    rows = [{"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "A", "phase_degrees": 0}]
    with pytest.raises(ValueError, match="kısa devre"):
        draft_to_netlist(rows)


def test_draft_to_netlist_rejects_duplicate_names():
    rows = [
        {"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "B", "phase_degrees": 0},
        {"name": "R1", "kind": "resistor", "value": 5, "node_a": "B", "node_b": "gnd", "phase_degrees": 0},
    ]
    with pytest.raises(ValueError, match="benzersiz"):
        draft_to_netlist(rows)


def test_draft_to_netlist_allows_ac_phase():
    rows = [{"name": "V1", "kind": "voltage_source", "value": 10, "node_a": "A", "node_b": "gnd", "phase_degrees": 30}]
    netlist = draft_to_netlist(rows)
    assert netlist.by_name("V1").phase == 30.0


# --- empedans kutusu (read_impedance) ---------------------------------------
#
# read_impedance kartezyen (R+jX) ya da kutupsal (Z∠θ) HANGISI YAZILIYSA onu
# okuyup Python'da (VLM'e hesap yaptirmadan) magnitude/phase_degrees'e
# cevirir -- _call_vlm_with_prompt monkeypatch'lenerek AG cagrisi olmadan
# test edilir.


def test_read_impedance_rectangular_form_converts_to_polar(monkeypatch):
    """'8+j6 Ω' -- gercek kisim 8, sanal kisim 6 -> |Z|=10, faz=36.8699 derece."""
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"resistance": 8, "reactance": 6, "magnitude": null, "phase_degrees": null}')
    out = read_impedance("fake_b64")
    assert out["value"] == pytest.approx(10.0, rel=1e-4)
    assert out["phase_degrees"] == pytest.approx(36.8699, rel=1e-3)


def test_read_impedance_negative_reactance_is_capacitive(monkeypatch):
    """'5-j3 Ω' -- negatif reaktans (kapasitif), faz NEGATIF cikmali."""
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"resistance": 5, "reactance": -3, "magnitude": null, "phase_degrees": null}')
    out = read_impedance("fake_b64")
    assert out["value"] == pytest.approx((5**2 + 3**2) ** 0.5, rel=1e-4)
    assert out["phase_degrees"] < 0


def test_read_impedance_polar_form_passed_through(monkeypatch):
    """'10∠30° Ω' -- zaten kutupsal, hesapsiz aynen donmeli."""
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"resistance": null, "reactance": null, "magnitude": 10, "phase_degrees": 30}')
    out = read_impedance("fake_b64")
    assert out["value"] == pytest.approx(10.0)
    assert out["phase_degrees"] == pytest.approx(30.0)


def test_read_impedance_missing_fields_raises(monkeypatch):
    """Ne kartezyen ne kutupsal alanlar doluysa (VLM emin degilse) tahmin
    YAPILMAZ -- acikca reddedilir."""
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"resistance": null, "reactance": null, "magnitude": null, "phase_degrees": null}')
    with pytest.raises(VLMReadError, match="eksik/null"):
        read_impedance("fake_b64")


# --- anahtar durumu (read_switch_state) -------------------------------------


def test_read_switch_state_closed(monkeypatch):
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"closed": true}')
    assert vlm_read.read_switch_state("fake_b64") == {"closed": True}


def test_read_switch_state_open(monkeypatch):
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"closed": false}')
    assert vlm_read.read_switch_state("fake_b64") == {"closed": False}


def test_read_switch_state_uncertain_raises(monkeypatch):
    """Emin degilse TAHMIN edilmez -- acikca reddedilir."""
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"closed": null}')
    with pytest.raises(VLMReadError, match="belirsiz"):
        vlm_read.read_switch_state("fake_b64")


# --- kontrol degiskeni hedefi (read_control_variable_target) ----------------
# BULUNDU (2026-08-24, Devre Fotoları 1-100/38.png): EasyOCR Yunanca'yi hic
# desteklemiyor, control_label_hint bu yuzden "iΔ" gibi etiketleri asla
# bulamiyordu. Her aday kirpima TEK TEK "bu etiket burada mi" ikili sorusu
# soruluyor -- coklu-gorselli tek cagri denendi ama VLM yanlis secti
# (28.png, bkz. fonksiyon docstring'i).


def _fake_label_probe(crops_with_label: set[str]):
    """crop b64'u `crops_with_label` icindeyse true donen sahte VLM probu."""
    return lambda b64, subscript: b64 in crops_with_label


def test_read_control_variable_target_single_hit(monkeypatch):
    monkeypatch.setattr(vlm_read, "crop_has_label", _fake_label_probe({"l1_b64"}))
    result = vlm_read.read_control_variable_target(
        "δ", [("resistor1", "r1_b64"), ("inductor1", "l1_b64")]
    )
    assert result == "inductor1"


def test_read_control_variable_target_no_hit_returns_none(monkeypatch):
    monkeypatch.setattr(vlm_read, "crop_has_label", _fake_label_probe(set()))
    assert vlm_read.read_control_variable_target("x", [("resistor1", "r1_b64")]) is None


def test_read_control_variable_target_multiple_hits_returns_none(monkeypatch):
    """Kirpim cerceveleri ORTUSTUGUNDE ayni etiket iki kirpimda birden
    gorunebiliyor (OLCULDU, 38.png) -- boyle bir durumda TAHMIN edip yanlis
    elemani secmek yerine BELIRSIZ deyip None donmeli."""
    monkeypatch.setattr(vlm_read, "crop_has_label", _fake_label_probe({"src_b64", "l1_b64"}))
    result = vlm_read.read_control_variable_target(
        "δ", [("source_i1", "src_b64"), ("inductor1", "l1_b64")]
    )
    assert result is None


def test_read_control_variable_target_empty_candidates_skips_call(monkeypatch):
    def _must_not_be_called(*a, **k):
        raise AssertionError("aday yokken VLM cagrilmamaliydi")

    monkeypatch.setattr(vlm_read, "crop_has_label", _must_not_be_called)
    assert vlm_read.read_control_variable_target("x", []) is None


def test_crop_has_label_parses_found_field(monkeypatch):
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"found": true}')
    assert vlm_read.crop_has_label("fake_b64", "x") is True
    monkeypatch.setattr(vlm_read, "_call_vlm_with_prompt", lambda *a, **k: '{"found": false}')
    assert vlm_read.crop_has_label("fake_b64", "x") is False


def test_bare_j_unit_counts_as_ohm():
    """Birimsiz "j2" yaziminda model birim yerine "j" donebiliyor -- bu bir
    reaktans (ohm), Henry/Farad degil."""
    for unit in ("j", "jω", "JW", " jomega "):
        assert vlm_read.is_ohm_unit(unit)
        assert vlm_read._unit_multiplier(unit) == 1.0


def test_unit_implies_kind():
    """Birim eleman turunu ima eder; ohm ETMEZ (direnc de fazor reaktansi da
    ohm ile yazilir)."""
    assert vlm_read.unit_implies_kind("V") == "voltage_source"
    assert vlm_read.unit_implies_kind("mA") == "current_source"
    assert vlm_read.unit_implies_kind("uF") == "capacitor"
    assert vlm_read.unit_implies_kind("mH") == "inductor"
    assert vlm_read.unit_implies_kind("ohm") is None
    assert vlm_read.unit_implies_kind("Ω") is None
    assert vlm_read.unit_implies_kind(None) is None
    assert vlm_read.unit_implies_kind("") is None


def test_looks_like_symbol_not_value():
    """OLCULDU (132-170/164.png): "I2"/"I1" etiketleri 12/11 SAYISI olarak
    donmustu -- ham yazi isimse okunan sayi gecersizdir."""
    for name in ("I2", "I1", "Vs", "iL", "R_eq", " io "):
        assert vlm_read.looks_like_symbol_not_value(name), name
    for value in ("5 kΩ", "30 V", "0.4 + j0.2 A", "16u0(t) mA", "j2 Ω", None, ""):
        assert not vlm_read.looks_like_symbol_not_value(value), value
