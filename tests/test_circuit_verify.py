from app.circuit.netlist import Element, Netlist
from app.circuit.problems import parse_answer_values
from app.circuit.verify import verify_netlist


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


# Oturumdaki gercek vaka: kullanicinin dogruladigi topoloji, 24 V -> 2.4 A / 10 ohm
CORRECT_TOPOLOGY = [
    V("s", "vs", "gnd", 24),
    R("6", "vs", "n1", 4),
    R("1", "n1", "gnd", 12),
    R("2", "n1", "n2", 8),
    R("3", "n2", "gnd", 12),
    R("4", "n2", "n3", 4),
    R("5", "n3", "gnd", 2),
]

# Ayni elemanlar, YANLIS okunmus topoloji: R2 ile R4 seri sanilmis
# (bu, bu projede gercekten yapilan hatanin ta kendisi).
WRONG_TOPOLOGY = [
    V("s", "vs", "gnd", 24),
    R("6", "vs", "n1", 4),
    R("1", "n1", "gnd", 12),
    R("2", "n1", "n2", 8),
    R("4", "n2", "n4", 4),
    R("3", "n4", "gnd", 12),
    R("5", "n4", "gnd", 2),
]


def test_confirms_correct_topology():
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), ((2.4, "A"),))
    assert result.verified is True
    assert result.matched == ((2.4, "A"),)


def test_rejects_wrong_topology_with_same_elements():
    """En kritik davranis: ayni elemanlarla yanlis okunan topoloji
    kitabin cevabini tutturmamali, yoksa dogrulama ise yaramaz."""
    result = verify_netlist(Netlist(list(WRONG_TOPOLOGY)), ((2.4, "A"),))
    assert result.verified is False
    assert result.unmatched == ((2.4, "A"),)


def test_matches_equivalent_resistance_answer():
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), ((10.0, "Ω"),))
    assert result.verified is True


def test_matches_node_voltage_answer():
    """Kitap dugum gerilimi verdiginde de dogrulanabilmeli (14.4 V = V(n1))."""
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), ((14.4, "V"),))
    assert result.verified is True


def test_requires_all_expected_values_to_match():
    """Birden fazla buyukluk verilmisse HEPSI tutmali -- tesadufi eslesmeye
    karsi koruma."""
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), ((2.4, "A"), (999.0, "V")))
    assert result.verified is False
    assert result.matched == ((2.4, "A"),)
    assert result.unmatched == ((999.0, "V"),)


def test_no_numeric_answer_is_not_silently_verified():
    """'Answer: Proof.' gibi sayisal olmayan cevaplar basarili sayilmamali."""
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), ())
    assert result.verified is False
    assert "sayısal cevap yok" in result.error


def test_solver_error_is_reported_not_swallowed():
    """Toprak dugumu olmayan devre: 'dogrulanamadi' demeli, sessizce
    basarisiz saymamali."""
    net = Netlist([V("s", "a", "b", 10), R("1", "a", "b", 5)])
    result = verify_netlist(net, ((2.0, "A"),))
    assert result.verified is False
    assert "toprak" in result.error


def test_works_with_answer_parsed_from_textbook_string():
    """Uctan uca: kitap metnindeki cevap -> ayristirma -> dogrulama."""
    expected = parse_answer_values("Answer: 2.4 A.")
    result = verify_netlist(Netlist(list(CORRECT_TOPOLOGY)), expected)
    assert result.verified is True


def test_describe_explains_failure():
    result = verify_netlist(Netlist(list(WRONG_TOPOLOGY)), ((2.4, "A"),))
    assert "Tutmadı" in result.describe()
