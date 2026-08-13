"""Netlist'i gerçek bir devre çözücüyle (ngspice/PySpice) çözer.

Neden ayrı bir çözücü: `topology.py` yalnızca seri/paralel indirgeme yapar
ve bu ders kitabı sorularının bir kısmına yetmez (köprü devreleri, düğüm/
çevre analizi gerektiren devreler indirgenemez). `docs/vision.md` kararı
gereği fizik/matematik burada yeniden icat edilmiyor; hazır kütüphane
kullanılıyor.

Bu modül, planlanan **öz-doğrulama döngüsünün** temel taşı: bir devrenin
topolojisi çıkarıldıktan sonra çözülüp kitabın bilinen cevabıyla
karşılaştırılabilsin diye. Karşılaştırma tutuyorsa topoloji okuması
doğrulanmış olur (kesin kanıt değil ama güçlü delil — bkz. `verify_answer`).

Kurulum notu: PySpice tek başına yetmiyor, ngspice paylaşımlı kütüphanesi
de gerekiyor:
    pip install PySpice
    pyspice-post-installation --install-ngspice-dll
"""

from dataclasses import dataclass, field

from app.circuit.netlist import Netlist

GROUND_NODES = {"gnd", "0", "ground", "toprak"}


class SolverError(RuntimeError):
    """Devre çözülemedi (eksik referans, tekil matris, ngspice hatası...)."""


@dataclass
class Solution:
    """Çözüm sonucu: düğüm gerilimleri ve kaynak akımları."""

    node_voltages: dict[str, float] = field(default_factory=dict)
    source_currents: dict[str, float] = field(default_factory=dict)

    def voltage_across(self, node_a: str, node_b: str) -> float:
        """İki düğüm arasındaki gerilim farkı (toprak 0 kabul edilir)."""
        return self._v(node_a) - self._v(node_b)

    def _v(self, node: str) -> float:
        if node.lower() in GROUND_NODES:
            return 0.0
        if node not in self.node_voltages:
            raise KeyError(f"{node!r} düğümü çözümde yok")
        return self.node_voltages[node]


def _ground_of(netlist: Netlist) -> str:
    """Devrenin referans (toprak) düğümü.

    ngspice bir referans düğüm ister. Netlist'te bilinen bir toprak adı
    yoksa çözüm anlamsız olur — sessizce rastgele bir düğüm seçmek yerine
    açık hata veriyoruz.
    """
    for node in netlist.nodes():
        if node.lower() in GROUND_NODES:
            return node
    raise SolverError(
        f"Devrede referans (toprak) düğümü yok. Beklenen adlardan biri kullanılmalı: "
        f"{sorted(GROUND_NODES)}. Mevcut düğümler: {sorted(netlist.nodes())}"
    )


def solve_dc(netlist: Netlist) -> Solution:
    """DC çalışma noktasını çözer (dirençler + DC kaynaklar).

    Kapasitör açık devre, bobin kısa devre kabul edilir — DC analizinin
    ders kitabı tanımı budur.
    """
    from PySpice.Spice.Netlist import Circuit  # ağır bağımlılık, gerektiğinde yüklensin

    ground = _ground_of(netlist)
    circuit = Circuit("devre")

    def node(name: str):
        return circuit.gnd if name == ground else name

    has_source = False
    for element in netlist.elements:
        a, b = element.nodes
        if element.value is None and element.kind != "capacitor":
            raise SolverError(f"{element.name}: değer verilmemiş, çözülemez")

        if element.kind == "resistor":
            circuit.R(element.name, node(a), node(b), element.value)
        elif element.kind == "voltage_source":
            circuit.V(element.name, node(a), node(b), element.value)
            has_source = True
        elif element.kind == "current_source":
            circuit.I(element.name, node(a), node(b), element.value)
            has_source = True
        elif element.kind == "capacitor":
            continue  # DC'de açık devre
        elif element.kind == "inductor":
            circuit.R(element.name, node(a), node(b), 1e-9)  # DC'de kısa devre
        else:
            raise SolverError(f"{element.name}: {element.kind} DC çözümde desteklenmiyor")

    if not has_source:
        raise SolverError("Devrede kaynak yok; çözülecek bir şey yok")

    try:
        analysis = circuit.simulator().operating_point()
    except Exception as exc:
        raise SolverError(f"ngspice çözemedi: {exc}") from exc

    voltages = {str(name): float(value[0]) for name, value in analysis.nodes.items()}

    # ngspice dal akımlarını kendi adlandırmasıyla döndürür: "R1" adlı gerilim
    # kaynağı "vr1" olur. Çağıran tarafın bunu bilmesi gerekmesin diye kendi
    # eleman adlarımıza geri eşliyoruz.
    # Ayrıca ngspice akımı kaynağa GİREN yönde verir; ders kitabı gösteriminde
    # kaynaktan ÇIKAN akım pozitiftir, o yüzden işaret çevriliyor.
    raw = {str(name).lower(): -float(value[0]) for name, value in analysis.branches.items()}
    currents = {
        element.name: raw[f"v{element.name}".lower()]
        for element in netlist.elements
        if element.kind == "voltage_source" and f"v{element.name}".lower() in raw
    }
    return Solution(node_voltages=voltages, source_currents=currents)


@dataclass(frozen=True)
class ElementResult:
    """Tek bir eleman için sonuçlar — öğrencinin asıl sorduğu şey bu.

    İşaret kuralı **pasif işaret kuralı** (ders kitabı standardı):
    akım, elemanın `nodes[0]→nodes[1]` yönünde pozitif; gerilim aynı yönde
    düşüş olarak alınır. Buna göre `power > 0` eleman güç HARCIYOR,
    `power < 0` güç VERİYOR demektir (kaynaklar tipik olarak negatiftir).
    """

    name: str
    kind: str
    current: float
    voltage: float
    power: float

    def describe(self) -> str:
        rol = "harcıyor" if self.power >= 0 else "veriyor"
        return (
            f"{self.name}: I = {self.current:.4g} A, V = {self.voltage:.4g} V, "
            f"P = {abs(self.power):.4g} W ({rol})"
        )


def element_results(netlist: Netlist, solution: Solution) -> dict[str, ElementResult]:
    """Her eleman için akım, gerilim ve gücü hesaplar.

    Eşdeğer direnç/toplam akım gibi devre geneli büyüklüklerin yanında,
    ders kitabı sorularının çoğu ELEMAN BAZLI şeyler sorar: "R3'ten geçen
    akım", "R2 üzerindeki gerilim", "kaynağın verdiği güç". Bu fonksiyon
    onları tek yerde üretir.
    """
    results: dict[str, ElementResult] = {}
    for element in netlist.elements:
        a, b = element.nodes
        voltage = solution.voltage_across(a, b)

        if element.kind == "resistor":
            current = voltage / element.value
        elif element.kind == "current_source":
            current = element.value
        elif element.kind == "voltage_source":
            # solve_dc kaynaktan ÇIKAN akımı pozitif veriyor; bu, kaynağın
            # içinden - ucundan + ucuna akan akımdır, yani nodes[0]→nodes[1]
            # yönünün TERSİ. Pasif işaret kuralına çevirmek için ters çevrilir.
            current = -solution.source_currents.get(element.name, 0.0)
        else:
            # Kapasitör DC'de açık devre, bobin kısa devre.
            current = 0.0 if element.kind == "capacitor" else voltage / 1e-9

        results[element.name] = ElementResult(
            name=element.name,
            kind=element.kind,
            current=current,
            voltage=voltage,
            power=voltage * current,
        )
    return results


def power_balance(results: dict[str, ElementResult]) -> float:
    """Tüm elemanların güçlerinin toplamı — korunum gereği 0 olmalı.

    Tellegen teoremi: harcanan güç = verilen güç. Sıfırdan belirgin sapma
    çözümün ya da netlist'in bozuk olduğunu gösterir; bu yüzden bağımsız
    bir tutarlılık kontrolü olarak kullanılabilir.
    """
    return sum(result.power for result in results.values())


def verify_answer(computed: float, expected: float, tolerance: float = 0.02) -> bool:
    """Hesaplanan değer kitabın cevabıyla uyuşuyor mu (bağıl tolerans).

    Ders kitapları yuvarlanmış değerler verir (örn. "2.4 A", "212.2 Ω"),
    bu yüzden birebir eşitlik aranmaz. Varsayılan %2 tolerans, yuvarlama
    farkını kabul ederken farklı bir topolojiden gelecek sapmayı yakalar.

    UYARI: eşleşme topolojinin doğru olduğunu KANITLAMAZ — farklı topolojiler
    aynı sayıyı verebilir. Güveni artırmak için birden fazla büyüklük
    (toplam akım + düğüm gerilimleri) karşılaştırılmalıdır.
    """
    if expected == 0:
        return abs(computed) <= tolerance
    return abs(computed - expected) / abs(expected) <= tolerance
