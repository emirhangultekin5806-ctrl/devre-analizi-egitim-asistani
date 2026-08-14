"""Ders kitabının GERÇEK şekillerini PDF'ten okuyup netlist'e çevirme.

`tests/test_textbook_circuits.py` aynı iki devreyi doğruluyor ama netlist'i
ELLE yazılmıştı. Buradaki fark: netlist'e hiç dokunulmuyor, doğrudan
şeklin vektör verisinden çıkarılıyor. Sonuç yine kitabın BASILI cevabıyla
karşılaştırılıyor — yani hem çıkarım hem çözüm aynı anda sınanıyor.

Cevaplar kitaptan (Sadiku vol.1):
  - Practice Problem 2.9  (Figure 2.36): Req = 6 Ω
  - Example 2.10          (Figure 2.37): Rab = 10 + 1.2 = 11.2 Ω
  - Example 3.1           (Figure 3.3):  v1 = 13.333 V, v2 = 20 V
  - Example 3.5           (Figure 3.18): I1 = 1 A, I2 = 1 A, I3 = 0
  - Example 2.6           (Figure 2.23): i = 8 A, vo = 48 V (bağımlı kaynak, VCVS)
  - Practice Problem 2.6  (Figure 2.24): vx = 10 V, vo = 5 V (bağımlı kaynak, VCVS)
  - Example 2.15          (Figure 2.52): Rab = 9.632 Ω, i = 12.458 A (köprü, Y-Δ gerektirir)
"""

from pathlib import Path

import pytest

from app.circuit.netlist import Netlist
from app.circuit.solve import element_results, power_balance, solve_dc
from app.circuit.topology import equivalent_resistance
from app.circuit.transient import rc_step_response
from app.vision.pdf_figure import extract_figure, extract_figures
from app.vision.schematic import SchematicError, build_netlist, build_switch_netlists

fitz = pytest.importorskip("fitz")

SADIKU_1 = Path(r"C:\Users\Sinemis\OneDrive\Masaüstü\ilovepdf_split\Devre analizi-1.pdf")
skip_no_sadiku_1 = pytest.mark.skipif(not SADIKU_1.exists(), reason="Sadiku vol1 PDF bu makinede yok")

# Her iki şekil de bu sayfada (Practice Problem 2.9 ve Example 2.10).
PAGE_INDEX = 79


@pytest.fixture(scope="module")
def page():
    with fitz.open(SADIKU_1) as document:
        yield document[PAGE_INDEX]


def solve(page, caption):
    netlist, terminals = build_netlist(extract_figure(page, caption))
    assert len(terminals) == 2, f"{caption}: iki dış uç bekleniyordu, {terminals} bulundu"
    first, second = terminals.values()
    return netlist, terminals, equivalent_resistance(netlist, first, second)


@skip_no_sadiku_1
@pytest.mark.parametrize(
    ("caption", "expected", "element_count"),
    [("Figure 2.36", 6.0, 8), ("Figure 2.37", 11.2, 8)],
)
def test_extracted_figure_matches_printed_answer(page, caption, expected, element_count):
    netlist, _, computed = solve(page, caption)
    assert len(netlist) == element_count
    assert computed == pytest.approx(expected, rel=1e-9), f"{caption}: {netlist.to_lines()}"


@skip_no_sadiku_1
def test_every_resistor_gets_a_value_from_the_figure(page):
    """Değersiz kalan bir eleman, etiket eşleşmesinin sessizce koptuğu demektir."""
    for caption in ("Figure 2.36", "Figure 2.37"):
        netlist, _ = build_netlist(extract_figure(page, caption))
        missing = [e.name for e in netlist.elements if e.value is None]
        assert not missing, f"{caption}: değersiz eleman {missing}"


@skip_no_sadiku_1
def test_terminals_take_their_letters_from_the_figure(page):
    """Fig 2.37'de uçlar 'a' ve 'b' olarak etiketli — Rab bu ikisi arasında."""
    _, terminals = build_netlist(extract_figure(page, "Figure 2.37"))
    assert set(terminals) == {"a", "b"}


@skip_no_sadiku_1
def test_only_the_two_terminals_are_left_dangling(page):
    """Başka açık uç varsa bir tel okunamamış demektir (sessiz topoloji hatası)."""
    netlist, terminals, _ = solve(page, "Figure 2.36")
    assert set(netlist.dangling_nodes()) <= set(terminals.values())


@skip_no_sadiku_1
def test_the_parallel_pair_the_book_names_is_present(page):
    """Kitap: "3 Ω ve 6 Ω dirençleri paraleldir, çünkü aynı iki düğüme bağlılar."

    Bu, cevabın sayısal olarak tutmasından bağımsız bir topoloji kanıtı:
    yanlış okunan bir şekil aynı sayıyı verebilir ama bu ilişkiyi vermez.
    """
    netlist, _ = build_netlist(extract_figure(page, "Figure 2.37"))
    three = next(e for e in netlist.elements if e.value == 3)
    six = next(e for e in netlist.elements if e.value == 6)
    assert set(three.nodes) == set(six.nodes)


@skip_no_sadiku_1
def test_a_caption_with_two_subfigures_is_reported_not_guessed(page):
    """Figure 2.35 (a) ve (b) iki ayrı devre — tek şekil sanılmamalı."""
    assert len(extract_figures(page, "Figure 2.35")) == 2
    with pytest.raises(SchematicError, match="ayrı çizim"):
        extract_figure(page, "Figure 2.35")


@skip_no_sadiku_1
def test_a_missing_caption_raises(page):
    with pytest.raises(SchematicError, match="başlığı bu sayfada yok"):
        extract_figure(page, "Figure 9.99")


# --- kaynaklı devreler -----------------------------------------------------
#
# Kaynak sembollerinin YÖNÜ (gerilimde +/- ucu, akımda ok yönü) sessizce
# yanlış okunabilecek tek şeydir: devre yine çözülür, sadece cevap yanlış
# çıkar. Bu yüzden doğrulama kitabın SAYISAL cevabıyla yapılıyor — yön ters
# okunsaydı bu testler tutmazdı.


@pytest.fixture(scope="module")
def document():
    with fitz.open(SADIKU_1) as opened:
        yield opened


@skip_no_sadiku_1
def test_current_source_direction_matches_example_3_1(document):
    """Example 3.1: iki akım kaynağı, çizilmiş toprak. Kitap: v1=13.333, v2=20."""
    figure = extract_figures(document[115], "Figure 3.3")[0]
    netlist, _ = build_netlist(figure)
    assert "gnd" in netlist.nodes(), "toprak sembolü okunamadı"
    solution = solve_dc(netlist)
    voltages = sorted(solution.node_voltages.values())
    assert voltages == pytest.approx([13.3333, 20.0], rel=1e-4)


@skip_no_sadiku_1
def test_both_drawings_of_one_circuit_give_the_same_netlist(document):
    """Fig 3.3 aynı devreyi (a) ve (b) olarak iki kez çiziyor.

    İkisinin aynı netlist'i vermesi, okumanın çizim biçimine değil devreye
    bağlı olduğunu gösterir — tek bir şeklin doğru çıkması şans olabilir.
    """
    first, second = extract_figures(document[115], "Figure 3.3")
    assert build_netlist(first)[0].to_lines() == build_netlist(second)[0].to_lines()


@skip_no_sadiku_1
def test_voltage_source_polarity_matches_example_3_5(document):
    """Example 3.5: 15 V ve 10 V kaynak. Kitap: I1=1 A, I2=1 A, I3=0.

    Tek bir kaynağın polaritesi ters okunsaydı akımlar bu değerleri
    vermezdi (çevre denklemi 15−5i₁−10(i₁−i₂)−10=0 işaret duyarlıdır).
    """
    figure = extract_figures(document[126], "Figure 3.18")[0]
    netlist, _ = build_netlist(figure)
    results = element_results(netlist, solve_dc(netlist, reference=min(netlist.nodes())))

    by_value = {element.value: element.name for element in netlist.elements}
    assert abs(results[by_value[5]].current) == pytest.approx(1.0, rel=1e-6)
    assert abs(results[by_value[6]].current) == pytest.approx(1.0, rel=1e-6)
    assert abs(results[by_value[4]].current) == pytest.approx(1.0, rel=1e-6)
    assert results[by_value[10]].current == pytest.approx(0.0, abs=1e-9)
    # 15 V kaynak devreyi sürüyor: güç VERİYOR (pasif işaret kuralında P<0)
    assert results[by_value[15]].power < 0
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


@skip_no_sadiku_1
def test_dependent_voltage_source_matches_example_2_6(document):
    """Example 2.6: tek çevrim, VCVS "2vo" 6Ω direncin gerilimiyle kontrollü.

    Kitabın metni bu sayfada font bozulmasından ("vo  48", "i  8 A") ötürü
    işaret belirsiz okunuyor; büyüklükler kesin: |i|=8A, |vo|=48V.
    """
    figure = extract_figures(document[72], "Figure 2.23")[0]
    netlist, _ = build_netlist(figure)
    vcvs = next(e for e in netlist.elements if e.kind == "vcvs")
    assert vcvs.control_nodes is not None
    results = element_results(netlist, solve_dc(netlist, reference=min(netlist.nodes())))
    assert abs(results[vcvs.name].current) == pytest.approx(8.0, rel=1e-6)
    six_ohm = next(e for e in netlist.elements if e.value == 6)
    assert abs(results[six_ohm.name].voltage) == pytest.approx(48.0, rel=1e-6)
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


@skip_no_sadiku_1
def test_dependent_voltage_source_matches_practice_problem_2_6(document):
    """Practice Problem 2.6: VCVS "2vx", 10Ω=vx ve 5Ω=vo seri. Kitap: vx=10V, vo=5V."""
    figure = extract_figures(document[72], "Figure 2.24")[0]
    netlist, _ = build_netlist(figure)
    vcvs = next(e for e in netlist.elements if e.kind == "vcvs")
    ten_ohm = next(e for e in netlist.elements if e.value == 10)
    five_ohm = next(e for e in netlist.elements if e.value == 5)
    assert vcvs.control_nodes == ten_ohm.nodes

    results = element_results(netlist, solve_dc(netlist, reference=min(netlist.nodes())))
    assert abs(results[ten_ohm.name].voltage) == pytest.approx(10.0, rel=1e-6)
    assert abs(results[five_ohm.name].voltage) == pytest.approx(5.0, rel=1e-6)
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


@skip_no_sadiku_1
def test_current_controlled_voltage_source_matches_example_3_6(document):
    """Example 3.6 (Figure 3.20): CCVS "4Io", kontrol akımı 10Ω direncin
    üzerinden bir OKLA ("Io") işaretli — +/- değil. Kitap: Io = 1.5 A.

    Bu devre bir köprü (4 düğüm, 6 dal) — hem CCVS okumasının hem de
    üçüncü elemanın (Rsense) doğru eşleştiğinin kanıtı: yön ya da eşleşme
    yanlış olsaydı 1.5 A çıkmazdı (elle doğrulandı: bkz. solve.py'deki
    "hayalet ampermetre" testleri).
    """
    figure = extract_figures(document[127], "Figure 3.20")[0]
    netlist, _ = build_netlist(figure)
    ccvs = next(e for e in netlist.elements if e.kind == "ccvs")
    sensed = netlist.by_name(ccvs.control_element)
    assert sensed.kind == "resistor"

    results = element_results(netlist, solve_dc(netlist, reference=min(netlist.nodes())))
    assert results[sensed.name].current == pytest.approx(1.5, rel=1e-6)
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


@skip_no_sadiku_1
def test_kcl_direction_arrows_are_not_mistaken_for_current_probes(document):
    """Example 3.1 (Figure 3.3) bağımlı kaynak İÇERMİYOR, ama KCL akım
    yönü için "i1"/"i2"/"i3" oklu etiketler var — bunlar sessizce bir
    "Io" akım probu sanılırsa bir direncin yönü (dolayısıyla raporlanan
    akım işareti) rastgele/kararsız hale gelirdi. Bu yüzden ayrım RAKAM
    alt indisli ("i3") ile HARF alt indisli ("Io") arasında yapılıyor.
    """
    first, second = extract_figures(document[115], "Figure 3.3")
    for symbol in (*first.symbols, *second.symbols):
        assert symbol.probe_is_current is False
    assert build_netlist(first)[0].to_lines() == build_netlist(second)[0].to_lines()


@skip_no_sadiku_1
def test_bridge_circuit_matches_example_2_15(document):
    """Example 2.15 (Figure 2.52): 6 dirençli, yıldız+üçgen karışık köprü.

    Seri/paralel TEK BAŞINA bu devreyi çözemez — kitabın kendisi de bunun
    için Y-Δ dönüşümü kullanıyor (§2.7). Kitabın cevabı: Rab = 9.632 Ω,
    i = 12.458 A. Bu, hem şekil okumanın hem yeni Y-Δ desteğinin BİRLİKTE
    doğru çalıştığının kanıtı — biri yanlış olsaydı sayı tutmazdı.
    """
    figure = extract_figures(document[87], "Figure 2.52")[0]
    netlist, terminals = build_netlist(figure)
    assert set(terminals) == {"a", "b"}

    resistors_only = Netlist([e for e in netlist.elements if e.kind == "resistor"])
    r_ab = equivalent_resistance(resistors_only, terminals["a"], terminals["b"])
    assert r_ab == pytest.approx(9.632, rel=1e-3)

    solution = solve_dc(netlist, reference=terminals["b"])
    source = next(e for e in netlist.elements if e.kind == "voltage_source")
    results = element_results(netlist, solution)
    assert abs(results[source.name].current) == pytest.approx(12.458, rel=1e-3)
    assert power_balance(results) == pytest.approx(0.0, abs=1e-9)


@skip_no_sadiku_1
def test_switch_and_capacitor_match_example_7_10(document):
    """Example 7.10 (Figure 7.43): SPDT anahtar + kapasitör, uçtan uca.

    `tests/test_circuit_transient.py`deki RC testleri netlist'i ELLE
    kurar; burada devre GERÇEKTEN şekilden okunuyor (kapasitör plaka
    sembolü + anahtar körü + iki kontak) ve `build_switch_netlists`
    "önce"/"sonra" netlist çiftini üretiyor. Kitabın cevabı: v(0)=15 V,
    v(∞)=30 V, τ=2 s, v(1)=20.9 V, v(4)=27.97 V — hiçbiri elle girilmedi.
    """
    figure = extract_figures(document[308], "Figure 7.43")[0]
    assert [s.kind for s in figure.symbols].count("capacitor") == 1
    assert figure.switch_blade is not None

    before, _, after, _ = build_switch_netlists(figure)
    ground = next(node for node in before.nodes() if node in after.nodes())
    response = rc_step_response(before, after, "C1", reference=ground)

    assert response.x0 == pytest.approx(15.0, rel=1e-3)
    assert response.x_inf == pytest.approx(30.0, rel=1e-3)
    assert response.tau == pytest.approx(2.0, rel=1e-3)
    assert response.at(1.0) == pytest.approx(20.9, rel=1e-3)
    assert response.at(4.0) == pytest.approx(27.97, rel=1e-3)
