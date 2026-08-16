import pytest

from app.vision.vlm_read import VLMReadError, draft_to_netlist, parse_vlm_response

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
