import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.topology import (
    equivalent_resistance,
    find_parallel_pair,
    find_series_pair,
    reduce_resistors,
)


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


# --- netlist dogrulamalari -------------------------------------------------


def test_element_rejects_same_node_both_ends():
    with pytest.raises(ValueError, match="kısa devre"):
        R("R1", "n1", "n1", 10)


def test_element_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Bilinmeyen eleman"):
        Element("X1", "transistor", ("a", "b"))


def test_netlist_rejects_duplicate_names():
    with pytest.raises(ValueError, match="benzersiz"):
        Netlist([R("R1", "a", "b", 1), R("R1", "b", "c", 2)])


def test_degree_counts_attached_elements():
    net = Netlist([R("R1", "a", "b", 1), R("R2", "b", "c", 2), R("R3", "b", "d", 3)])
    assert net.degree("b") == 3
    assert net.degree("a") == 1


def test_dangling_nodes_flags_open_ends():
    net = Netlist([R("R1", "a", "b", 1), R("R2", "b", "c", 2)])
    assert net.dangling_nodes() == ["a", "c"]


def test_to_lines_is_human_checkable():
    net = Netlist([R("R1", "n1", "n2", 100)])
    assert net.to_lines() == ["R1 = 100: n1-n2"]


# --- seri / paralel tanimi -------------------------------------------------


def test_series_requires_shared_node_of_degree_two():
    net = Netlist([R("R1", "a", "b", 1), R("R2", "b", "c", 2)])
    first, second, shared = find_series_pair(net)
    assert {first.name, second.name} == {"R1", "R2"}
    assert shared == "b"


def test_not_series_when_third_element_taps_the_node():
    """Kullanicinin ifadesiyle: 'aradan baska yone giden kablo varsa seri degildir'."""
    net = Netlist([R("R1", "a", "b", 1), R("R2", "b", "c", 2), R("R3", "b", "d", 3)])
    assert find_series_pair(net) is None


def test_parallel_requires_both_nodes_shared():
    net = Netlist([R("R1", "a", "b", 6), R("R2", "a", "b", 3)])
    first, second = find_parallel_pair(net)
    assert {first.name, second.name} == {"R1", "R2"}


def test_not_parallel_when_only_one_node_shared():
    net = Netlist([R("R1", "a", "b", 6), R("R2", "b", "c", 3)])
    assert find_parallel_pair(net) is None


# --- indirgeme -------------------------------------------------------------


def test_series_reduction_adds_values():
    net = Netlist([R("R1", "a", "b", 4), R("R2", "b", "c", 6)])
    reduced, steps = reduce_resistors(net)
    assert len(reduced.elements) == 1
    assert reduced.elements[0].value == 10
    assert steps[0].kind == "seri"


def test_parallel_reduction_uses_product_over_sum():
    net = Netlist([R("R1", "a", "b", 6), R("R2", "a", "b", 3)])
    reduced, _ = reduce_resistors(net)
    assert reduced.elements[0].value == pytest.approx(2.0)


def test_bridge_circuit_is_not_fully_reducible():
    """Wheatstone koprusu seri/paralel ile indirgenemez -- sessizce yanlis
    sonuc vermek yerine indirgenemedigi anlasilmali."""
    net = Netlist(
        [
            R("R1", "a", "b", 1),
            R("R2", "a", "c", 1),
            R("R3", "b", "d", 1),
            R("R4", "c", "d", 1),
            R("R5", "b", "c", 1),  # kopru kolu
        ]
    )
    reduced, _ = reduce_resistors(net, protected_nodes=("a", "d"))
    assert len(reduced.elements) > 1
    assert equivalent_resistance(net, "a", "d") is None


# --- gercek devre: oturumda kullanicinin dogruladigi ornek ------------------


# Bu devre bu projede canli bir hata vakasiydi: topoloji "goze bakarak"
# okunup R2 ile R4 seri sanilmisti; kullanici duzeltti. Dogruladigi topoloji:
#   R4+R5 seri -> R3'e paralel -> R2'ye seri -> R1'e paralel -> R6'ya seri
# ve sonuc: toplam 10 ohm, 24 V kaynakta 2.4 A.
#
# NOT: Fotograftaki DIRENC DEGERLERI elimizde yok; asagidaki degerler
# dogrulanmis topolojiyi koruyacak ve dogrulanmis 10 ohm sonucunu verecek
# sekilde secildi. Yani test topolojiyi ve indirgeme sirasini dogruluyor,
# fotograftaki sayilari degil.
_VERIFIED_TOPOLOGY = [
    R("R6", "vs", "n1", 4),
    R("R1", "n1", "gnd", 12),
    R("R2", "n1", "n2", 8),
    R("R3", "n2", "gnd", 12),
    R("R4", "n2", "n3", 4),
    R("R5", "n3", "gnd", 2),
]


def test_real_circuit_from_user_photo():
    total = equivalent_resistance(Netlist(list(_VERIFIED_TOPOLOGY)), "vs", "gnd")
    assert total == pytest.approx(10.0)
    assert 24.0 / total == pytest.approx(2.4)


def test_real_circuit_reduction_order_is_reported():
    _, steps = reduce_resistors(Netlist(list(_VERIFIED_TOPOLOGY)), protected_nodes=("vs", "gnd"))
    # Ilk adim R4+R5 serisi olmali (n3 dugumunun derecesi 2)
    assert steps[0].kind == "seri"
    assert set(steps[0].combined) == {"R4", "R5"}
    assert steps[0].result_value == pytest.approx(6.0)
    # Adimlar ogrenciye gosterilebilir olmali
    assert "→" in steps[0].describe()
