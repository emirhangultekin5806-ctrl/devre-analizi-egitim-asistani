import pytest

from app.circuit.mesh import MeshAnalysisError, find_loops, solve_mesh
from app.circuit.netlist import Element, Netlist
from app.circuit.solve import solve_dc
from app.circuit.verify import cross_check_methods


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


def V(name, plus, minus, value):
    return Element(name, "voltage_source", (plus, minus), value)


DIVIDER = [V("s", "vs", "gnd", 10), R("1", "vs", "mid", 5), R("2", "mid", "gnd", 5)]

# Kullanicinin dogruladigi gercek devre (24 V -> 2.4 A)
REAL_CIRCUIT = [
    V("s", "vs", "gnd", 24),
    R("6", "vs", "n1", 4),
    R("1", "n1", "gnd", 12),
    R("2", "n1", "n2", 8),
    R("3", "n2", "gnd", 12),
    R("4", "n2", "n3", 4),
    R("5", "n3", "gnd", 2),
]

# Seri/paralel ile INDIRGENEMEYEN kopru -- cevre analizinin asil degeri burada
BRIDGE = [
    V("s", "a", "gnd", 10),
    R("1", "a", "b", 1),
    R("2", "a", "c", 2),
    R("3", "b", "gnd", 3),
    R("4", "c", "gnd", 4),
    R("5", "b", "c", 5),
]


# --- cevre bulma -----------------------------------------------------------


def test_loop_count_matches_euler_formula():
    """Bagimsiz cevre sayisi = eleman - dugum + 1."""
    net = Netlist(list(BRIDGE))
    expected = len(net.elements) - len(net.nodes()) + 1
    assert len(find_loops(net)) == expected


def test_rejects_disconnected_circuit():
    net = Netlist([V("s", "a", "gnd", 10), R("1", "x", "y", 5)])
    with pytest.raises(MeshAnalysisError, match="bağlantısız"):
        solve_mesh(net)


def test_rejects_unsupported_element_kind():
    net = Netlist([V("s", "a", "gnd", 10), Element("C1", "capacitor", ("a", "gnd"), 1e-6)])
    with pytest.raises(MeshAnalysisError, match="Desteklenmeyen"):
        solve_mesh(net)


def test_rejects_element_without_value():
    net = Netlist([V("s", "a", "gnd", 10), Element("R1", "resistor", ("a", "gnd"))])
    with pytest.raises(MeshAnalysisError, match="Değeri verilmemiş"):
        solve_mesh(net)


# --- cozum dogrulugu -------------------------------------------------------


def test_divider_current():
    assert abs(solve_mesh(Netlist(list(DIVIDER)))["s"]) == pytest.approx(1.0, rel=1e-6)


def test_real_circuit_matches_verified_answer():
    assert abs(solve_mesh(Netlist(list(REAL_CIRCUIT)))["s"]) == pytest.approx(2.4, rel=1e-6)


def test_solves_bridge_that_series_parallel_cannot_reduce():
    current = abs(solve_mesh(Netlist(list(BRIDGE)))["s"])
    assert current == pytest.approx(abs(solve_dc(Netlist(list(BRIDGE))).source_currents["s"]), rel=1e-6)


# --- IKI YONTEMIN CAPRAZ KONTROLU (kullanicinin onerisi) -------------------


@pytest.mark.parametrize(
    ("label", "elements"),
    [("bolucu", DIVIDER), ("gercek devre", REAL_CIRCUIT), ("kopru", BRIDGE)],
)
def test_nodal_and_mesh_agree(label, elements):
    """Dugum analizi (KCL, ngspice) ile cevre analizi (KVL, bizim) ayni
    sonuca varmali. Kitabin cevabina ihtiyac duymayan bir dogrulama."""
    result = cross_check_methods(Netlist(list(elements)))
    assert result.agree is True, f"{label}: {result.describe()}"


def test_disagreement_is_reported_not_hidden():
    """Yontemlerden biri uygulanamiyorsa sessizce 'uyustu' sayilmamali."""
    net = Netlist([V("s", "a", "gnd", 10), Element("C1", "capacitor", ("a", "gnd"), 1e-6)])
    result = cross_check_methods(net)
    assert result.agree is False
    assert "çevre analizi" in result.error


# --- SUPERMESH: akim kaynagi destegi ---------------------------------------


def I(name, a, b, value):
    return Element(name, "current_source", (a, b), value)


def _resistor_currents_from_nodal(net):
    """Dugum gerilimlerinden direnc akimlarini hesaplar (karsilastirma icin)."""
    solution = solve_dc(net)
    currents = {}
    for element in net.elements:
        if element.kind != "resistor":
            continue
        a, b = element.nodes
        va = 0.0 if a == "gnd" else solution.node_voltages[a]
        vb = 0.0 if b == "gnd" else solution.node_voltages[b]
        currents[element.name] = (va - vb) / element.value
    return currents


@pytest.mark.parametrize(
    ("label", "elements"),
    [
        ("tek akim kaynagi", [I("i1", "gnd", "a", 2), R("1", "a", "gnd", 5), R("2", "a", "gnd", 5)]),
        (
            "supermesh: akim kaynagi iki cevrede ortak",
            [
                V("s", "a", "gnd", 10),
                R("1", "a", "b", 2),
                I("i1", "b", "c", 3),
                R("2", "c", "gnd", 4),
                R("3", "b", "gnd", 6),
            ],
        ),
        (
            "akim + gerilim kaynagi birlikte",
            [
                V("s", "a", "gnd", 12),
                R("1", "a", "b", 3),
                R("2", "b", "gnd", 6),
                I("i1", "gnd", "b", 1),
            ],
        ),
    ],
)
def test_supermesh_matches_nodal_analysis(label, elements):
    """Akim kaynagi iceren devrelerde de iki yontem ayni sonucu vermeli.

    Supermesh, agac secimiyle cozuluyor: akim kaynaklari agacin disinda
    birakildigi icin her biri kendi cevresini tanimliyor ve o cevrenin
    akimi dogrudan biliniyor.
    """
    net = Netlist(list(elements))
    expected = _resistor_currents_from_nodal(net)
    actual = solve_mesh(net)
    for name, value in expected.items():
        assert actual[name] == pytest.approx(value, abs=1e-6), f"{label}: {name}"
