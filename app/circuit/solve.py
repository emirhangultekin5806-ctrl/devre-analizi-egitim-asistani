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
    # Gerilimlerin ölçüldüğü referans düğüm. Toprak sembolü olmayan
    # şekillerde bu, çağıranın seçtiği düğümdür; çözümde 0 V'tur ve
    # ngspice çıktısında yer almaz.
    reference: str | None = None

    def voltage_across(self, node_a: str, node_b: str) -> float:
        """İki düğüm arasındaki gerilim farkı (referans 0 kabul edilir)."""
        return self._v(node_a) - self._v(node_b)

    def _v(self, node: str) -> float:
        # ngspice düğüm adlarını küçük harfe çeviriyor (SPICE büyük/küçük
        # harf duyarsızdır); `node_voltages` bu yüzden hep küçük harfle
        # anahtarlanır (bkz. `solve_dc`) — sorgu da aynı şekilde küçük
        # harfe çevrilir, aksi halde büyük harfli bir düğüm adı burada
        # sessizce KeyError verirdi (aynı hata sınıfı `ac.py`/`threephase.py`
        # geçmişinde bir kez yakalanmıştı, DC tarafında da gerçek veride
        # tekrarlandı — bkz. `app/vision/vlm_read.py` ile üretilen büyük
        # harfli düğüm adları).
        key = node.lower()
        if key in GROUND_NODES or (self.reference is not None and key == self.reference.lower()):
            return 0.0
        if key not in self.node_voltages:
            raise KeyError(f"{node!r} düğümü çözümde yok")
        return self.node_voltages[key]


def _ground_of(netlist: Netlist, reference: str | None = None) -> str:
    """Devrenin referans (toprak) düğümü.

    ngspice bir referans düğüm ister. Netlist'te bilinen bir toprak adı
    yoksa çözüm anlamsız olur — sessizce rastgele bir düğüm seçmek yerine
    açık hata veriyoruz.

    `reference` verilirse o düğüm referans alınır. Ders kitabı şekillerinin
    çoğunda toprak sembolü ÇİZİLMEZ (soru "şu daldaki akım" biçiminde
    sorulur); referansın seçimi düğüm gerilimlerini kaydırır ama eleman
    akım/gerilim/güçlerini değiştirmez, o yüzden çağıran taraf serbestçe
    seçebilir. Yine de varsayılan olarak seçmiyoruz: sessiz varsayım yerine
    açık tercih.
    """
    if reference is not None:
        if reference not in netlist.nodes():
            raise SolverError(
                f"{reference!r} düğümü devrede yok. Mevcut: {sorted(netlist.nodes())}"
            )
        return reference
    for node in netlist.nodes():
        if node.lower() in GROUND_NODES:
            return node
    raise SolverError(
        f"Devrede referans (toprak) düğümü yok. Beklenen adlardan biri kullanılmalı: "
        f"{sorted(GROUND_NODES)}. Mevcut düğümler: {sorted(netlist.nodes())}. "
        f"Şekilde toprak çizilmemişse `reference=` ile bir düğüm seçin."
    )


def solve_dc(netlist: Netlist, reference: str | None = None) -> Solution:
    """DC çalışma noktasını çözer (dirençler + DC kaynaklar).

    Kapasitör açık devre, bobin kısa devre kabul edilir — DC analizinin
    ders kitabı tanımı budur.

    `reference`: şekilde toprak çizilmemişse referans alınacak düğüm
    (bkz. `_ground_of`).
    """
    from PySpice.Spice.Netlist import Circuit  # ağır bağımlılık, gerektiğinde yüklensin

    ground = _ground_of(netlist, reference)
    circuit = Circuit("devre")

    def node(name: str):
        return circuit.gnd if name == ground else name

    # CCVS/CCCS gibi AKIM kontrollü kaynaklar SPICE'ta yalnızca bir gerilim
    # kaynağının dal akımını referans alabilir. Kontrol edilen eleman bir
    # direnç olduğunda, klasik "hayalet ampermetre" hilesi kullanılır: o
    # direncin bir ucu, aralarına 0 V'luk bir kaynak konarak hayali bir ara
    # düğüme kaydırılır. Bu kaynağın dal akımı, direncin GERÇEK akımına
    # eşittir (0 V'luk kaynak ideal, düğümde başka çıkış yok). Öğrenciye
    # gösterilen sonuçlar etkilenmez: hayalet düğümün gerilimi, direncin asıl
    # ikinci ucuyla (0 V'luk kaynak üzerinden) her zaman aynıdır.
    sensed = {e.control_element for e in netlist.elements if e.control_element is not None}
    resistor_names = {e.name for e in netlist.elements if e.kind == "resistor"}
    if sensed - resistor_names:
        raise SolverError(
            "Kontrol akımı yalnızca bir DİRENCİN üzerinden ölçülebiliyor (bu sürümde); "
            f"eşleşmeyen: {sorted(sensed - resistor_names)}"
        )

    has_source = False
    for element in netlist.elements:
        a, b = element.nodes
        if element.value is None and element.kind != "capacitor":
            raise SolverError(f"{element.name}: değer verilmemiş, çözülemez")
        # 0 Ω direnç fiziksel olarak anlamsız (kısa devre farklı bir eleman
        # türüdür) VE element_results()'ta bölme hatası verir -- OLCULDU
        # (Figure 2.23): VLM/OCR'ın Ω'yi "0" yanlış okuması bu değeri
        # sessizce geçirip ZeroDivisionError ile programı çökertti. Açık
        # hata burada, ngspice'a gitmeden önce.
        if element.kind == "resistor" and element.value == 0:
            raise SolverError(f"{element.name}: direnç değeri 0 -- muhtemelen okuma hatası, çözülemez")

        if element.kind == "resistor":
            if element.name in sensed:
                phantom = f"__amm_{element.name}"
                circuit.R(element.name, node(a), phantom, element.value)
                circuit.V(f"amm_{element.name}", phantom, node(b), 0)
            else:
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
        elif element.kind == "vcvs":
            nc_plus, nc_minus = element.control_nodes
            circuit.VCVS(
                element.name, node(a), node(b), node(nc_plus), node(nc_minus), element.value
            )
            has_source = True
        elif element.kind == "ccvs":
            circuit.CCVS(
                element.name, node(a), node(b), f"vamm_{element.control_element}", element.value
            )
            has_source = True
        else:
            raise SolverError(f"{element.name}: {element.kind} DC çözümde desteklenmiyor")


    if not has_source:
        raise SolverError("Devrede kaynak yok; çözülecek bir şey yok")

    try:
        analysis = circuit.simulator().operating_point()
    except Exception as exc:
        raise SolverError(f"ngspice çözemedi: {exc}") from exc

    # Küçük harf: ngspice düğüm adlarını (SPICE büyük/küçük harf duyarsız
    # olduğu için) sessizce küçük harfe çeviriyor — burada da AÇIKÇA küçük
    # harfe çevrilip anahtarlanır, `Solution._v()`'nin sorgu tarafında
    # yaptığı küçültmeyle SİMETRİK olsun diye (bkz. `ac.py`'deki aynı desen).
    voltages = {str(name).lower(): float(value[0]) for name, value in analysis.nodes.items()}

    # ngspice dal akımlarını kendi adlandırmasıyla döndürür: "R1" adlı gerilim
    # kaynağı "vr1" olur, VCVS ise "er1" (SPICE eleman öneki + isim). Çağıran
    # tarafın bunu bilmesi gerekmesin diye kendi eleman adlarımıza geri
    # eşliyoruz.
    # Ayrıca ngspice akımı kaynağa GİREN yönde verir; ders kitabı gösteriminde
    # kaynaktan ÇIKAN akım pozitiftir, o yüzden işaret çevriliyor.
    raw = {str(name).lower(): -float(value[0]) for name, value in analysis.branches.items()}
    currents = {
        element.name: raw[f"{_BRANCH_PREFIX[element.kind]}{element.name}".lower()]
        for element in netlist.elements
        if element.kind in _BRANCH_PREFIX
        and f"{_BRANCH_PREFIX[element.kind]}{element.name}".lower() in raw
    }
    return Solution(node_voltages=voltages, source_currents=currents, reference=ground)


# SPICE eleman öneki: ngspice dal akımını bu önek + eleman adıyla adlandırır.
_BRANCH_PREFIX = {"voltage_source": "v", "vcvs": "e", "ccvs": "h"}


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
        elif element.kind in ("voltage_source", "vcvs", "ccvs"):
            # solve_dc kaynaktan ÇIKAN akımı pozitif veriyor; bu, kaynağın
            # içinden - ucundan + ucuna akan akımdır, yani nodes[0]→nodes[1]
            # yönünün TERSİ. Pasif işaret kuralına çevirmek için ters çevrilir.
            # VCVS ve CCVS için de aynı kural geçerli — ngspice "e"/"h"
            # dallarını da "v" ile aynı yönde raporluyor (gerçek devrede
            # doğrulandı, bkz. solve.py testleri).
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
