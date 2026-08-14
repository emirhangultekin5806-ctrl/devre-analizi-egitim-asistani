import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.topology import (
    delta_to_wye,
    equivalent_resistance,
    find_parallel_pair,
    find_series_pair,
    find_wye_center,
    reduce_resistors,
    transform_wye_to_delta,
    wye_to_delta,
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


def test_bridge_circuit_needs_wye_delta_not_just_series_parallel():
    """Wheatstone koprusunde seri/paralel TEK BASINA tikanir (b ve c'nin
    ucer direnci var, hicbiri ne seri ne paralel kosulunu saglar)."""
    net = Netlist(
        [
            R("R1", "a", "b", 1),
            R("R2", "a", "c", 1),
            R("R3", "b", "d", 1),
            R("R4", "c", "d", 1),
            R("R5", "b", "c", 1),  # kopru kolu
        ]
    )
    assert find_series_pair(net, protected_nodes=("a", "d")) is None
    assert find_parallel_pair(net) is None


def test_bridge_circuit_reduces_via_wye_delta():
    """Ayni kopru, yildiz-ucgen devreye girince tam indirgenir.

    Dengeli koprude (R1/R3 = R2/R4) teorik sonuc bilinir: kopru kolundan
    (R5) akim gecmez, Rad = (R1+R3) ∥ (R2+R4) = 2 ∥ 2 = 1 Ω. Y-Δ
    donusumunun kendisi bir yaklastirma degil TAM bir denklik oldugu icin
    bu deger her R5 icin ayni cikmali; testte R5=1 ile dogrulaniyor.
    """
    net = Netlist(
        [
            R("R1", "a", "b", 1),
            R("R2", "a", "c", 1),
            R("R3", "b", "d", 1),
            R("R4", "c", "d", 1),
            R("R5", "b", "c", 1),
        ]
    )
    reduced, steps = reduce_resistors(net, protected_nodes=("a", "d"))
    assert len(reduced.elements) == 1
    assert reduced.elements[0].value == pytest.approx(1.0)
    assert equivalent_resistance(net, "a", "d") == pytest.approx(1.0)
    assert any(hasattr(step, "center_node") for step in steps), "Y-Δ adımı beklenirdi"


# --- yildiz-ucgen (Y-Delta) donusumu ----------------------------------------
#
# Formuller Sadiku Bolum 2.7'den; sayisal degerler kitabin kendi
# ornekleriyle birebir dogrulandi (asagida).


def test_delta_to_wye_matches_example_2_14():
    """Sadiku Example 2.14: Rab=10, Rbc=25, Rca=15 -> Y = {3, 5, 7.5} Ω."""
    r_a, r_b, r_c = delta_to_wye(10, 25, 15)
    assert sorted((r_a, r_b, r_c)) == pytest.approx(sorted((3.0, 5.0, 7.5)))


def test_wye_to_delta_matches_practice_problem_2_14():
    """Sadiku Practice Problem 2.14: Ra=10, Rb=20, Rc=40 -> Δ = {140, 70, 35} Ω."""
    r_ab, r_bc, r_ca = wye_to_delta(10, 20, 40)
    assert sorted((r_ab, r_bc, r_ca)) == pytest.approx(sorted((140.0, 70.0, 35.0)))


def test_delta_to_wye_and_back_round_trips():
    """İki dönüşüm birbirinin tersi olmalı — bağımsız bir tutarlılık kontrolü."""
    original = (12.0, 7.0, 19.0)
    wye = delta_to_wye(*original)
    back = wye_to_delta(*wye)
    assert sorted(back) == pytest.approx(sorted(original))


def test_find_wye_center_requires_exactly_three_resistors():
    net = Netlist([R("R1", "a", "n", 1), R("R2", "b", "n", 1), R("R3", "c", "n", 1)])
    assert find_wye_center(net) == "n"

    # 4. direnc eklenince artik "tam olarak 3" kosulu bozulur.
    net_with_four = Netlist([*net.elements, R("R4", "d", "n", 1)])
    assert find_wye_center(net_with_four) is None


def test_find_wye_center_respects_protected_nodes():
    """Dis uc bir yildiz merkezi gibi gorunse bile kaldirilamaz."""
    net = Netlist([R("R1", "a", "n", 1), R("R2", "b", "n", 1), R("R3", "c", "n", 1)])
    assert find_wye_center(net, protected_nodes=("n",)) is None


def test_transform_wye_to_delta_removes_the_center_node():
    net = Netlist([R("R1", "a", "n", 10), R("R2", "b", "n", 20), R("R3", "c", "n", 40)])
    new_netlist, step = transform_wye_to_delta(net, "n", counter=1)
    assert "n" not in new_netlist.nodes()
    assert len(new_netlist.elements) == 3
    assert sorted(e.value for e in new_netlist.elements) == pytest.approx(
        sorted((140.0, 70.0, 35.0))
    )
    assert step.center_node == "n"
    assert step.combined == ("R1", "R2", "R3")
    assert "yıldız→üçgen" in step.describe()


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
