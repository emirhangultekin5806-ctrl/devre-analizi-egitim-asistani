"""Şematik geometri -> netlist çıkarımı, PDF olmadan.

Geometri elle yazıldığı için burada "şekli doğru okudum mu" belirsizliği
yok: girdi kesin, dolayısıyla bir hata çıkarsa topoloji mantığındadır.
PDF'ten okuma ayrı test ediliyor (`test_pdf_figure.py`).
"""

import pytest

from app.vision.schematic import (
    Figure,
    Label,
    SchematicError,
    Symbol,
    Terminal,
    Wire,
    assign_values,
    build_netlist,
    join_hops,
)


def resistor(x0, y0, x1, y1):
    return Symbol("resistor", (x0, y0, x1, y1))


def ohm(value, x, y):
    return Label(f"{value} Ω", (x, y), value=float(value), unit="ohm")


# --- temel topoloji --------------------------------------------------------


def test_two_resistors_on_one_wire_are_in_series():
    """Bir sembol üzerinden geçen teli KESER: iki yanı ayrı düğümdür."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[resistor(20, -3, 36, 3), resistor(60, -3, 76, 3)],
        labels=[ohm(10, 28, -10), ohm(20, 68, -10)],
    )
    netlist, _ = build_netlist(figure)
    assert len(netlist) == 2
    assert len(netlist.nodes()) == 3  # seri iki eleman -> 3 düğüm
    shared = set(netlist.elements[0].nodes) & set(netlist.elements[1].nodes)
    assert len(shared) == 1
    assert netlist.degree(shared.pop()) == 2  # ortak düğüme başka eleman yok


def test_two_resistors_between_the_same_rails_are_in_parallel():
    figure = Figure(
        wires=[
            Wire((0, 0), (100, 0)),  # üst ray
            Wire((0, 60), (100, 60)),  # alt ray
            Wire((30, 0), (30, 60)),  # sol dikey
            Wire((70, 0), (70, 60)),  # sağ dikey
        ],
        symbols=[resistor(27, 22, 33, 38), resistor(67, 22, 73, 38)],
        labels=[ohm(4, 40, 30), ohm(12, 80, 30)],
    )
    netlist, _ = build_netlist(figure)
    first, second = netlist.elements
    assert set(first.nodes) == set(second.nodes)  # her iki ucu da ortak


def test_terminals_map_to_the_outer_nodes():
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[resistor(40, -3, 56, 3)],
        terminals=[Terminal((0, 0), "a"), Terminal((100, 0), "b")],
        labels=[ohm(7, 48, -10)],
    )
    netlist, terminals = build_netlist(figure)
    assert set(terminals) == {"a", "b"}
    assert terminals["a"] != terminals["b"]
    assert set(netlist.elements[0].nodes) == set(terminals.values())


def test_a_resistor_reached_by_two_separate_stub_wires_gets_two_pins():
    """Bir direncin iki ucuna, ortada BİRLEŞMEYEN iki AYRI tel bağlanabilir
    (her uca kendi telinden — tek, sembolün içinden geçen bir tel yerine).
    Bu, Sadiku Figure 7.43'te (4kΩ direnç) karşılaşılan, önceden desteklenmeyen
    ama elektriksel olarak tamamen geçerli bir çizim biçimidir."""
    figure = Figure(
        wires=[Wire((0, 0), (45, 0)), Wire((100, 0), (55, 0))],  # sembolün İÇİNDE biten iki güdük
        symbols=[resistor(40, -3, 60, 3)],
        labels=[ohm(7, 50, -10)],
    )
    netlist, _ = build_netlist(figure)
    assert len(netlist) == 1
    assert len(netlist.nodes()) == 2
    assert netlist.elements[0].value == 7.0


def test_a_resistor_reached_by_only_one_stub_wire_is_rejected():
    """Tek güdük tel bir sembole yalnızca BİR ucundan değerse öbür uç boşta
    kalır — bu sessizce geçilmemeli, açık hata verilmeli."""
    figure = Figure(
        wires=[Wire((0, 0), (45, 0))],
        symbols=[resistor(40, -3, 60, 3)],
        labels=[ohm(7, 50, -10)],
    )
    with pytest.raises(SchematicError, match="boşta"):
        build_netlist(figure)


def test_close_but_separate_wire_ends_do_not_falsely_merge():
    """İki AYRI telin uçları birbirine yakın (ama T birleşimi oluşturacak
    kadar değil) düşerse birleşmemeli. Ölçülen gerçek örnek: Figure 7.43'te
    anahtarın gövde teli, B kontağının teline 0.49pt kadar yaklaşıyordu ama
    aralarında görünür boşluk vardı — geniş toleransla yanlışlıkla
    birleştiriliyordu (bkz. `ENDPOINT_JOIN_TOLERANCE`)."""
    figure = Figure(
        wires=[Wire((0, 0), (50, 0)), Wire((50.4, 0), (100, 0))],
        symbols=[resistor(10, -3, 30, 3), resistor(70, -3, 90, 3)],
        labels=[ohm(1, 20, -10), ohm(2, 80, -10)],
    )
    netlist, _ = build_netlist(figure)
    assert len(netlist.nodes()) == 4  # iki direnç arasında GERÇEK bir boşluk var


# --- kesişme kuralı (şematik okumanın en kritik yeri) ----------------------


CROSSING = {
    "wires": [Wire((0, 50), (100, 50)), Wire((50, 0), (50, 100))],
    "symbols": [resistor(20, 47, 36, 53), resistor(47, 70, 53, 86)],
    "labels": [Label("1 Ω", (28, 40), 1.0, "ohm"), Label("2 Ω", (60, 78), 2.0, "ohm")],
}


def test_wires_that_merely_cross_are_not_connected():
    """Nokta yoksa çapraz geçen teller AYRI düğümdür (çizim kuralı)."""
    netlist, _ = build_netlist(Figure(**CROSSING))
    assert len(netlist.nodes()) == 4


def test_a_junction_dot_at_the_crossing_connects_them():
    netlist, _ = build_netlist(Figure(**CROSSING, dots=[(50, 50)]))
    assert len(netlist.nodes()) == 3


def test_a_wire_end_touching_another_wire_connects_without_a_dot():
    """T birleşimi: uç değiyorsa nokta gerekmez."""
    figure = Figure(
        wires=[Wire((0, 50), (100, 50)), Wire((50, 50), (50, 100))],
        symbols=[resistor(20, 47, 36, 53), resistor(47, 70, 53, 86)],
        labels=[Label("1 Ω", (28, 40), 1.0, "ohm"), Label("2 Ω", (60, 78), 2.0, "ohm")],
    )
    netlist, _ = build_netlist(figure)
    assert len(netlist.nodes()) == 3


# --- atlama (hop) boşluğu --------------------------------------------------


def test_hop_gap_over_a_crossing_wire_is_closed():
    """Kesişmeyi atlamak için boşluk bırakılan tel elektriksel olarak süreklidir."""
    wires = [
        Wire((0, 0), (44, 0)),  # boşluğun solu
        Wire((56, 0), (100, 0)),  # boşluğun sağı
        Wire((50, -30), (50, 30)),  # boşluktan geçen tel
    ]
    joined = join_hops(wires)
    assert len(joined) == 2
    spans = sorted(wire.length() for wire in joined)
    assert spans[1] == pytest.approx(100.0)  # iki parça tek tele indi


def test_a_plain_gap_without_a_crossing_stays_open():
    """Kesişme yoksa boşluk atlama değildir — birleştirilmemeli."""
    wires = [Wire((0, 0), (44, 0)), Wire((56, 0), (100, 0))]
    assert len(join_hops(wires)) == 2


def test_a_resistor_gap_is_not_mistaken_for_a_hop():
    """Eleman gövdesi de tele boşluk açar; atlama sanılırsa devre kısa devre olur."""
    wires = [Wire((0, 0), (100, 0))]
    assert join_hops(wires) == wires


# --- yönlü elemanlar (kaynaklar) -------------------------------------------


def source(kind, x0, y0, x1, y1, orientation, value):
    return Symbol(kind, (x0, y0, x1, y1), value=value, orientation=orientation)


def test_source_orientation_decides_which_end_is_node_zero():
    """`nodes[0]` gerilim kaynağında ARTI uçtur; ters yazılırsa işaretler döner."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        # orientation = (-1, 0): artı uç solda
        symbols=[source("voltage_source", 43, -7, 57, 7, (-1.0, 0.0), 9.0)],
        terminals=[Terminal((0, 0), "sol"), Terminal((100, 0), "sag")],
    )
    netlist, terminals = build_netlist(figure)
    assert netlist.elements[0].nodes == (terminals["sol"], terminals["sag"])


def test_reversing_the_orientation_reverses_the_nodes():
    def build(orientation):
        figure = Figure(
            wires=[Wire((0, 0), (100, 0))],
            symbols=[source("voltage_source", 43, -7, 57, 7, orientation, 9.0)],
        )
        return build_netlist(figure)[0].elements[0].nodes

    assert build((-1.0, 0.0)) == build((1.0, 0.0))[::-1]


def test_vertical_source_orientation_uses_the_y_axis():
    figure = Figure(
        wires=[Wire((0, 0), (0, 100))],
        # orientation = (0, -1): artı uç yukarıda (PDF'te y aşağı doğru artar)
        symbols=[source("voltage_source", -7, 43, 7, 57, (0.0, -1.0), 12.0)],
        terminals=[Terminal((0, 0), "ust"), Terminal((0, 100), "alt")],
    )
    netlist, terminals = build_netlist(figure)
    assert netlist.elements[0].nodes == (terminals["ust"], terminals["alt"])


def test_a_resistor_ignores_orientation_ordering():
    """Yönsüz elemanda sıra anlamsız; orientation None ise dokunulmaz."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[resistor(43, -3, 57, 3)],
        labels=[ohm(10, 50, -10)],
    )
    assert build_netlist(figure)[0].elements[0].value == 10.0


# --- toprak ----------------------------------------------------------------


def test_ground_symbol_names_its_node_gnd():
    figure = Figure(
        wires=[Wire((0, 0), (100, 0)), Wire((100, 0), (100, 40))],
        symbols=[resistor(43, -3, 57, 3)],
        labels=[ohm(10, 50, -10)],
        grounds=[(100, 40)],
    )
    netlist, _ = build_netlist(figure)
    assert "gnd" in netlist.nodes()


def test_two_ground_symbols_mean_the_same_node():
    """Şematik kuralı: şekildeki her toprak sembolü AYNI düğümü gösterir.

    İki uçta ayrı çizilmiş topraklar tek düğüme inmezse devre kapanmaz ve
    iki eleman seri yerine iki ayrı kol gibi görünür.
    """
    figure = Figure(
        wires=[Wire((0, 0), (200, 0)), Wire((0, 0), (0, 40)), Wire((200, 0), (200, 40))],
        symbols=[resistor(43, -3, 57, 3), resistor(143, -3, 157, 3)],
        labels=[ohm(10, 50, -10), ohm(20, 150, -10)],
        grounds=[(0, 40), (200, 40)],
    )
    netlist, _ = build_netlist(figure)
    assert sorted(netlist.nodes()) == ["gnd", "n1"]
    for element in netlist.elements:
        assert "gnd" in element.nodes


# --- bağlar (yay ile çizilen bağlantılar) ----------------------------------


def test_a_link_connects_its_two_ends_without_touching_anything_between():
    """Atlama yayı: iki ucu birleştirir, altından geçen tele DEĞMEZ."""
    figure = Figure(
        wires=[
            Wire((0, 0), (40, 0)),  # atlayan telin solu
            Wire((60, 0), (100, 0)),  # sağı
            Wire((50, -30), (50, 30)),  # altından geçen tel
            Wire((50, 30), (150, 30)),  # geçen telin devamı (eleman için)
        ],
        symbols=[resistor(15, -3, 31, 3), resistor(100, 27, 116, 33)],
        labels=[Label("1 Ω", (23, -10), 1.0, "ohm"), Label("2 Ω", (108, 20), 2.0, "ohm")],
        links=[Wire((40, 0), (45, -6)), Wire((45, -6), (55, -6)), Wire((55, -6), (60, 0))],
    )
    netlist, _ = build_netlist(figure)
    left = next(e for e in netlist.elements if e.value == 1)
    # Atlanan tel bağlanmamalı: dikey tel kendi düğümlerinde kalmalı
    assert len(netlist.nodes()) == 4, netlist.to_lines()
    assert left.nodes[0] != left.nodes[1]


def test_chained_links_only_connect_their_outer_ends():
    from app.vision.schematic import chain_links

    chained = chain_links([Wire((0, 0), (5, -6)), Wire((5, -6), (15, -6)), Wire((15, -6), (20, 0))])
    assert len(chained) == 1
    assert {chained[0].p1, chained[0].p2} == {(0, 0), (20, 0)}


# --- bağımlı kaynaklar (control_ref / probe_key eşleşmesi) -----------------


def test_dependent_source_control_nodes_come_from_the_probed_resistor():
    """VCVS'in control_nodes'u, eşleşen probe_key'e sahip elemanın (yön
    çözümlenmiş) kendi düğümleri olmalı."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[
            Symbol("vcvs", (10, -5, 26, 5), value=2.0, control_ref="x"),
            Symbol("resistor", (60, -3, 76, 3), orientation=(1.0, 0.0), probe_key="x"),
        ],
    )
    netlist, _ = build_netlist(figure)
    vcvs = netlist.by_name("E1")
    resistor_element = netlist.by_name("R1")
    assert vcvs.control_nodes == resistor_element.nodes


def test_reversing_the_probed_resistor_reverses_control_nodes():
    def control_nodes_for(orientation):
        figure = Figure(
            wires=[Wire((0, 0), (100, 0))],
            symbols=[
                Symbol("vcvs", (10, -5, 26, 5), value=2.0, control_ref="x"),
                Symbol("resistor", (60, -3, 76, 3), orientation=orientation, probe_key="x"),
            ],
        )
        return build_netlist(figure)[0].by_name("E1").control_nodes

    assert control_nodes_for((1.0, 0.0)) == control_nodes_for((-1.0, 0.0))[::-1]


def test_ccvs_control_element_comes_from_the_current_probed_resistor():
    """CCVS'in control_element'i, probe_is_current=True olan eşleşen
    elemanın ADI olmalı (VCVS'teki gibi düğüm çifti değil)."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[
            Symbol("ccvs", (10, -5, 26, 5), value=4.0, control_ref="o"),
            Symbol(
                "resistor",
                (60, -3, 76, 3),
                orientation=(1.0, 0.0),
                probe_key="o",
                probe_is_current=True,
            ),
        ],
    )
    netlist, _ = build_netlist(figure)
    ccvs = netlist.by_name("H1")
    sensed = netlist.by_name("R1")
    assert ccvs.control_element == sensed.name
    assert ccvs.control_nodes is None


def test_an_unmatched_control_ref_raises():
    """Kontrol edilen büyüklüğü sağlayan bir eleman şekilde işaretli değilse
    sessizce yanlış bağlamak yerine hata verilmeli."""
    figure = Figure(
        wires=[Wire((0, 0), (100, 0))],
        symbols=[
            Symbol("vcvs", (10, -5, 26, 5), value=2.0, control_ref="x"),
            resistor(60, -3, 76, 3),  # probe_key yok
        ],
        labels=[ohm(10, 68, -10)],
    )
    with pytest.raises(SchematicError, match="hiçbir elemanın"):
        build_netlist(figure)


# --- etiket eşleştirme -----------------------------------------------------


def test_values_go_to_the_nearest_symbol():
    symbols = [resistor(0, 0, 16, 4), resistor(100, 0, 116, 4)]
    resolved = assign_values(symbols, [ohm(5, 8, -10), ohm(9, 108, -10)])
    assert [s.value for s in resolved] == [5.0, 9.0]


def test_a_volt_label_is_never_given_to_a_resistor():
    """Birim kontrolü olmadan en yakınlık kuralı kaynak değerini dirence yazardı."""
    symbols = [resistor(0, 0, 16, 4)]
    volts = Label("12 V", (8, -6), value=12.0, unit="volt")
    ohms = Label("30 Ω", (8, -40), value=30.0, unit="ohm")
    assert assign_values(symbols, [volts, ohms])[0].value == 30.0


def test_one_label_cannot_serve_two_symbols():
    symbols = [resistor(0, 0, 16, 4), resistor(20, 0, 36, 4)]
    resolved = assign_values(symbols, [ohm(5, 18, -10)])
    assert sorted(s.value is None for s in resolved) == [False, True]


# --- hata durumları (sessiz yanlış cevap yerine açık hata) -----------------


def test_a_symbol_off_the_wires_raises():
    figure = Figure(wires=[Wire((0, 0), (100, 0))], symbols=[resistor(20, 200, 36, 216)])
    with pytest.raises(SchematicError, match="hiçbir telin üzerinde değil"):
        build_netlist(figure)


def test_a_symbol_covering_two_wires_raises():
    figure = Figure(
        wires=[Wire((0, 0), (100, 0)), Wire((0, 10), (100, 10))],
        symbols=[resistor(20, -3, 36, 13)],
    )
    with pytest.raises(SchematicError, match="belirsiz"):
        build_netlist(figure)


def test_a_figure_without_symbols_raises():
    with pytest.raises(SchematicError, match="eleman sembolü bulunamadı"):
        build_netlist(Figure(wires=[Wire((0, 0), (10, 0))]))


def test_a_figure_without_wires_raises():
    with pytest.raises(SchematicError, match="tel bulunamadı"):
        build_netlist(Figure(symbols=[resistor(0, 0, 16, 4)]))
