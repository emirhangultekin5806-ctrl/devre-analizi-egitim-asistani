"""Şematik geometrisinden devre topolojisi çıkarımı — saf geometri, PDF'siz.

Neden bu modül var: ders kitabı şekillerini "okumak" için bir görsel model
eğitmeyi planlıyorduk (yüzlerce etiketli örnek gerektiren, olasılıksal bir
yol). Ölçüm bunu gereksiz kıldı: Sadiku'nun PDF'indeki şekiller **saf
vektör** — tek bir raster görüntü bile yok, her tel bir doğru parçası ve
her direnç bir zikzak yolu olarak, tam koordinatlarıyla duruyor. Bağlantı
çıkarımı bu durumda tanıma değil, GEOMETRİ problemidir: deterministik ve
kesin.

Bu modül bilerek PyMuPDF'e bağlı değildir; girdisi sade geometrik
ilkellerdir (`Wire`, `Symbol`, `Label`, nokta listeleri). Böylece topoloji
mantığı PDF olmadan, elle yazılmış geometriyle test edilebilir —
`pdf_figure.py` yalnızca PDF'ten bu ilkelleri üretir.

Şematik çizim kuralları (uluslararası, kitaba özel değil) burada
kurallaştırılmıştır:

- Bir sembolün üzerinden geçen tel, sembol tarafından **kesilir**: sembolün
  iki yanındaki parçalar farklı düğümlerdir (yoksa her eleman kısa devre
  olurdu).
- Bir telin UCU başka bir telin üstüne değiyorsa bağlantı vardır (T
  birleşimi).
- İki tel birbirini ortasından KESİYORSA bağlantı **yoktur** — ancak
  kesişme noktasında bir birleşim noktası (dolu daire) varsa vardır. Bu
  ayrım şematik okumanın en kritik kuralıdır; atlanırsa çapraz geçen teller
  sessizce birleştirilir ve devre tamamen yanlış çözülür.
- Aynı kuralın diğer yarısı: kesişmede bağlantı OLMADIĞINI göstermek için
  tellerden biri küçük bir boşlukla (atlama/hop) çizilir. O boşluk kopukluk
  değildir — tel elektriksel olarak devam eder. Fig 2.37'de ölçüldü: 9 pt'lik
  boşluk, tam olarak diğer çaprazın geçtiği noktada.
"""

import math
from dataclasses import dataclass, field

from app.circuit.netlist import Element, Netlist

# Koordinatlar PDF punto (pt) cinsinden. Kitabın çizimlerinde tel uçları
# birbirine 0.1 pt hassasiyetle oturuyor; 1.5 pt tolerans yuvarlama ve
# çizgi kalınlığı payını karşılar, ayrı düğümleri (en yakın ayrı tel ~14 pt)
# birleştirmeye yetecek kadar büyük değildir.
POINT_TOLERANCE = 1.5

# İki AYRI telin uç uca (kendi ikisinin de UCUYLA) değmesi için tolerans.
# POINT_TOLERANCE'tan SIKI: gerçek uç-uca temaslar ~0.1pt hassasiyetle
# oturuyor (yukarıdaki not), ama 1.5pt'lik geniş tolerans, aslında
# birbirine değMEyen iki bağımsız ucu da (örn. Figure 7.43'te anahtarın
# gövde teliyle B kontağının teli arası 0.49pt) yanlışlıkla birleştirebiliyor.
# T birleşimleri (bir ucun ötekinin ORTASINA değmesi) bu sıkı toleransa
# TABİ DEĞİL — bkz. `_touch_on_wire`.
ENDPOINT_JOIN_TOLERANCE = 0.3

# Sembol gövdesinin telden ayırdığı bölge, sembol sınırından bu kadar
# genişletilir: zikzak yolu bazen telin ucuyla tam örtüşmez.
SYMBOL_PAD = 0.5

# Atlama (hop) boşluğunun en büyük genişliği. Ölçülen: 9 pt. Bir eleman
# gövdesi en az 16.7 pt yer kapladığı için bu eşik, elemanla açtığı boşluğu
# atlama sanma riskini taşımaz — ayrıca atlama için kesişme de aranır.
HOP_MAX_GAP = 12.0

# Toprak sembolünün üst çizgisi ile tel arasındaki en büyük mesafe.
GROUND_SNAP = 6.0


@dataclass(frozen=True)
class Wire:
    """Bir iletken doğru parçası (şekildeki düz çizgi)."""

    p1: tuple[float, float]
    p2: tuple[float, float]

    def length(self) -> float:
        return math.dist(self.p1, self.p2)

    def point_at(self, t: float) -> tuple[float, float]:
        return (
            self.p1[0] + t * (self.p2[0] - self.p1[0]),
            self.p1[1] + t * (self.p2[1] - self.p1[1]),
        )


@dataclass(frozen=True)
class Symbol:
    """Bir devre elemanının şekildeki gövdesi (sınır kutusu + türü).

    `orientation`, yönü olan elemanlar (kaynaklar) için gereklidir: sembolün
    merkezinden `nodes[0]` olacak uca doğru bakan vektör. Gerilim kaynağında
    bu **+** ucudur; akım kaynağında SPICE'ın `I n+ n- ` kuralı gereği okun
    TERSİ yöndeki uçtur (akım kaynağın içinde n+'dan n-'ye akar, ok da o
    yönü gösterir). Yönsüz elemanlarda (direnç) None'dır.
    """

    kind: str  # netlist.ELEMENT_KINDS içinden
    rect: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    value: float | None = None
    name: str | None = None
    orientation: tuple[float, float] | None = None
    # Bağımlı kaynak desteği: "2vx" etiketli bir kaynağın `control_ref`'i
    # "vx" olur — bu, ihtiyaç duyduğu kontrol geriliminin ANAHTARIdır.
    # Kontrol edilen büyüklüğü SAĞLAYAN eleman (genelde bir direnç) ise aynı
    # anahtarı `probe_key` alanında taşır ("+ vx −" etiketiyle şekilde
    # işaretli). `build_netlist` bu iki alanı eşleştirerek bağımlı kaynağın
    # `control_nodes`'unu bulur — ayrı bir alanda tutulması, normal bir
    # direncin YÖNÜNÜ (orientation, kendi +/- işaretinden) bağımsız olarak
    # taşıyabilmesi içindir.
    control_ref: str | None = None
    probe_key: str | None = None
    # Prob GERİLİM mi AKIM mı sağlıyor ("+ vx −" işareti mi, yoksa okla
    # işaretli "Io" mu)? True ise `build_netlist` bu elemanın kendi ADINI
    # (`control_element`) verir, False ise kendi düğüm çiftini
    # (`control_nodes`) verir — CCVS/VCVS ayrımının netlist'e yansıması bu.
    probe_is_current: bool = False

    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.rect
        return ((x0 + x1) / 2, (y0 + y1) / 2)


@dataclass(frozen=True)
class Label:
    """Şekildeki bir metin etiketi (örn. "6 Ω" ya da düğüm adı "a")."""

    text: str
    center: tuple[float, float]
    value: float | None = None  # SI temel biriminde (ohm, volt, amper...)
    unit: str | None = None  # "ohm" | "volt" | "amper" | "farad" | "henry"


# Hangi birim hangi eleman türüne ait. Etiket-sembol eşleştirmesi bu tabloya
# uyar: "12 V" etiketi bir dirence, "6 Ω" bir kaynağa atanamaz. Birim
# kontrolü olmadan en yakınlık kuralı, kaynak ile direncin yan yana durduğu
# şekillerde sessizce yanlış değer verir.
UNIT_KINDS = {
    "ohm": "resistor",
    "volt": "voltage_source",
    "amper": "current_source",
    "farad": "capacitor",
    "henry": "inductor",
}


@dataclass(frozen=True)
class Terminal:
    """Şeklin dış ucu (küçük boş daire) — eşdeğer direnç bunlar arasında sorulur.

    `name` şekilde uca yazılmış harf varsa odur ("a", "b"); yoksa None.
    """

    point: tuple[float, float]
    name: str | None = None


@dataclass
class Figure:
    """Tek bir devre şeklinin ham geometrisi."""

    wires: list[Wire] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    dots: list[tuple[float, float]] = field(default_factory=list)
    terminals: list[Terminal] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    # Toprak sembollerinin tele değdiği noktalar. Çözücü bir referans düğüm
    # istiyor; şekilde toprak çizilmişse düğüm adı "gnd" olur.
    grounds: list[tuple[float, float]] = field(default_factory=list)
    # BAĞ: iki ucu elektriksel olarak birleştiren, ama geometrik olarak yer
    # KAPLAMAYAN bağlantı. Çizimdeki yaylar (yuvarlatılmış köşeler ve
    # kesişme atlamaları) böyle modellenir. Yay düz bir tel gibi ele
    # alınırsa kirişi yakınından geçen tellere yalancı temas üretiyor:
    # Fig 2.37'de atlama yayının kirişi, atlanan çaprazın tam üstünden
    # geçtiği için devreyi kısa devre ediyordu.
    links: list[Wire] = field(default_factory=list)
    # SPDT anahtar körü: ORTAK uçtan (p1) ŞU AN dokunduğu kontağa (p2)
    # çizilen gerçek çizgi. `build_switch_netlists` bu TEK çizimden
    # "önce" (kör p2'ye değiyor) ve "sonra" (kör diğer kontağa değiyor,
    # `figure.terminals`'tan bulunur) netlist çiftini üretir. Genel bir
    # "wire" gibi ele alınırsa anahtarın hangi konumda olduğu bilgisi
    # kaybolur (kör sessizce sıradan bir bağlantıya karışır).
    switch_blade: Wire | None = None


class SchematicError(RuntimeError):
    """Şekil güvenilir biçimde okunamadı.

    Sessizce yanlış bir netlist üretmektense hata veriyoruz: yanlış netlist
    doğru görünen ama yanlış bir cevaba yol açar, ve bu proje tam olarak o
    hatayı önlemek için kuruldu (bkz. `app/circuit/netlist.py`).
    """


# --- geometri yardımcıları -------------------------------------------------


def _distance_to_segment(point: tuple[float, float], wire: Wire) -> float:
    """Noktanın doğru PARÇASINA (sonsuz doğruya değil) uzaklığı."""
    (x0, y0), (x1, y1) = wire.p1, wire.p2
    dx, dy = x1 - x0, y1 - y0
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return math.dist(point, wire.p1)
    t = ((point[0] - x0) * dx + (point[1] - y0) * dy) / denominator
    t = max(0.0, min(1.0, t))
    return math.dist(point, (x0 + t * dx, y0 + t * dy))


def _crossing_point(a: Wire, b: Wire) -> tuple[float, float] | None:
    """İki parçanın GERÇEK kesişme noktası; paralel/kesişmiyorsa None."""
    (ax0, ay0), (ax1, ay1) = a.p1, a.p2
    (bx0, by0), (bx1, by1) = b.p1, b.p2
    adx, ady = ax1 - ax0, ay1 - ay0
    bdx, bdy = bx1 - bx0, by1 - by0
    denominator = adx * bdy - ady * bdx
    if abs(denominator) < 1e-9:
        return None  # paralel ya da çakışık
    t = ((bx0 - ax0) * bdy - (by0 - ay0) * bdx) / denominator
    u = ((bx0 - ax0) * ady - (by0 - ay0) * adx) / denominator
    if not (0 <= t <= 1 and 0 <= u <= 1):
        return None
    return (ax0 + t * adx, ay0 + t * ady)


def _clip_to_rect(
    wire: Wire, rect: tuple[float, float, float, float], pad: float
) -> tuple[float, float] | None:
    """Telin dikdörtgen içinde kalan parçasının [t0, t1] aralığı.

    Liang-Barsky kırpması. Kesişme yoksa None.
    """
    x0, y0, x1, y1 = rect
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    dx = wire.p2[0] - wire.p1[0]
    dy = wire.p2[1] - wire.p1[1]
    t_min, t_max = 0.0, 1.0
    for p, q in (
        (-dx, wire.p1[0] - x0),
        (dx, x1 - wire.p1[0]),
        (-dy, wire.p1[1] - y0),
        (dy, y1 - wire.p1[1]),
    ):
        if abs(p) < 1e-12:
            if q < 0:
                return None  # tel dilime paralel ve dışında
            continue
        r = q / p
        if p < 0:
            if r > t_max:
                return None
            t_min = max(t_min, r)
        else:
            if r < t_min:
                return None
            t_max = min(t_max, r)
    return (t_min, t_max)


# --- birleşim-bulma (union-find) -------------------------------------------


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


# --- atlama (hop) boşluklarını kapatma -------------------------------------


def _hop_gap(a: Wire, b: Wire) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """İki tel aynı doğru üzerinde ve aralarında küçük bir boşluk mu var?

    Dönen: boşluğu kapatan uç çifti, yoksa None.
    """
    a_direction = (a.p2[0] - a.p1[0], a.p2[1] - a.p1[1])
    b_direction = (b.p2[0] - b.p1[0], b.p2[1] - b.p1[1])
    a_length, b_length = a.length(), b.length()
    if a_length == 0 or b_length == 0:
        return None
    cross = a_direction[0] * b_direction[1] - a_direction[1] * b_direction[0]
    if abs(cross) / (a_length * b_length) > 0.02:
        return None  # paralel değil

    closest = min(
        ((math.dist(p, q), p, q) for p in (a.p1, a.p2) for q in (b.p1, b.p2)),
        key=lambda item: item[0],
    )
    distance, point_a, point_b = closest
    # Alt sınır POINT_TOLERANCE olmalı, sıfır değil: uç uca DEĞEN iki eş
    # doğrultulu tel zaten bağlıdır ve birleştirilirse o noktadaki T
    # birleşimi yok olur — birleşen tel artık orada bitmeyip içinden geçer,
    # dolayısıyla üçüncü telle "ortadan kesişme" durumuna düşer ve bağlantı
    # kaybolur. Fig 3.3(a)'da devre tam olarak böyle iki parçaya ayrılıyordu
    # (kayan nokta gürültüsü yüzünden mesafe 0 değil ~1e-4 çıkıyor).
    if not (POINT_TOLERANCE < distance <= HOP_MAX_GAP):
        return None
    # Aynı DOĞRU üzerinde olmalı: b'nin ucu a'nın doğrultusundan sapmamalı.
    offset = (point_b[0] - a.p1[0], point_b[1] - a.p1[1])
    perpendicular = abs(offset[0] * a_direction[1] - offset[1] * a_direction[0]) / a_length
    if perpendicular > POINT_TOLERANCE:
        return None
    return point_a, point_b


def join_hops(wires: list[Wire]) -> list[Wire]:
    """Kesişmeyi atlamak için boşlukla çizilmiş telleri tek tele birleştirir.

    Boşluğun ATLAMA olduğunun kanıtı, boşluktan başka bir telin geçmesidir —
    bu şart olmadan, gerçekten kopuk (açık uçlu) iki tel de birleştirilirdi.
    """
    groups = _DisjointSet(len(wires))
    for i, first in enumerate(wires):
        for j in range(i + 1, len(wires)):
            gap = _hop_gap(first, wires[j])
            if gap is None:
                continue
            bridge = Wire(*gap)
            crosses = any(
                _crossing_point(bridge, wires[k]) is not None
                for k in range(len(wires))
                if k not in (i, j)
            )
            if crosses:
                groups.union(i, j)

    merged: dict[int, list[tuple[float, float]]] = {}
    for index, wire in enumerate(wires):
        merged.setdefault(groups.find(index), []).extend((wire.p1, wire.p2))
    result = []
    for points in merged.values():
        if len(points) == 2:
            result.append(Wire(points[0], points[1]))
            continue
        far = max(
            ((math.dist(p, q), p, q) for p in points for q in points), key=lambda item: item[0]
        )
        result.append(Wire(far[1], far[2]))
    return result


def chain_links(links: list[Wire]) -> list[Wire]:
    """Uç uca eklenmiş yayları tek bir bağa indirger.

    Kesişme atlaması tek bir yay değil, uç uca birkaç yay parçasıyla
    çiziliyor ve ARA uçları tam olarak atlanan telin üstüne düşüyor —
    atlamanın tanımı gereği öyle olmak zorunda. Ara uçlar bağlantı noktası
    sayılırsa atlanan tel yanlışlıkla birleştirilir; Fig 2.37 tam olarak
    böyle kısa devre oluyordu. Yalnızca zincirin DIŞ uçları bağlantı kurar.
    """
    if not links:
        return []
    groups = _DisjointSet(len(links))
    for i, first in enumerate(links):
        for j in range(i + 1, len(links)):
            second = links[j]
            if any(
                math.dist(p, q) <= POINT_TOLERANCE
                for p in (first.p1, first.p2)
                for q in (second.p1, second.p2)
            ):
                groups.union(i, j)

    members: dict[int, list[int]] = {}
    for index in range(len(links)):
        members.setdefault(groups.find(index), []).append(index)

    result: list[Wire] = []
    for indices in members.values():
        if len(indices) == 1:
            result.append(links[indices[0]])
            continue
        endpoints: list[tuple[tuple[float, float], int]] = []
        for index in indices:
            for point in (links[index].p1, links[index].p2):
                for position, (existing, count) in enumerate(endpoints):
                    if math.dist(point, existing) <= POINT_TOLERANCE:
                        endpoints[position] = (existing, count + 1)
                        break
                else:
                    endpoints.append((point, 1))
        outer = [point for point, count in endpoints if count == 1]
        if len(outer) == 2:
            result.append(Wire(outer[0], outer[1]))
        else:
            # Halka ya da çatal: hangi uçların dış olduğu belirsiz, olduğu
            # gibi bırakılır (yanlış bir sadeleştirme yapmaktansa).
            result.extend(links[index] for index in indices)
    return result


# --- telleri sembollerde kesme ---------------------------------------------


@dataclass
class _Fragment:
    """Sembollerle kesildikten sonra kalan iletken parçası."""

    wire: Wire
    # Bu parçanın uçlarına dayanan semboller: (sembol indeksi, uç no 0|1)
    pins: list[tuple[int, int]] = field(default_factory=list)


def _split_wires(figure: Figure) -> tuple[list[_Fragment], dict[tuple[int, int], tuple[float, float]]]:
    """Her teli üzerinden geçen sembollerde keser, parçaları döndürür.

    Sembolün iki yanında kalan parçalar AYRI düğümlerdir — elemanın uçları
    da bu iki parçaya bağlanır.

    Uçların KONUMU da döndürülür: yönü olan elemanlarda (kaynaklar) hangi
    ucun `nodes[0]` olacağı, ucun sembole göre hangi yönde durduğuna bakarak
    belirlenir.

    Bir tel sembolün İÇİNDE bir uçla BİTEBİLİR de (sembole tek taraftan
    "sap" gibi yaklaşan bir tel — örn. bir direncin iki ucuna, ortada
    birleşmeyen iki AYRI tel parçasıyla bağlanıldığı, yaygın bir çizim
    biçimi). Bu durumda tel sembole yalnızca TEK bir temas noktası verir
    (girdiği sınır noktasında); sembolün içinde kalan güdük kısım gerçek
    bir bağlantı değildir, atılır. Böylece bir sembol ya TEK bir telin
    içinden geçmesiyle (2 temas, aynı telden) ya da İKİ AYRI telin birer
    ucuyla dokunmasıyla (1+1 temas, iki farklı telden) tam olarak 2 uca
    kavuşabilir — ikisi de geçerlidir, toplam temas sayısı 2 olmalıdır.
    """
    fragments: list[_Fragment] = []
    pin_positions: dict[tuple[int, int], tuple[float, float]] = {}
    # Her sembolün kaç kez bir telle TEMAS ettiği izlenir (geçiş=2, sap=1):
    # bir eleman tam olarak 2 uçla temas etmeli, aksi halde okuma belirsizdir.
    touches_per_symbol: dict[int, int] = dict.fromkeys(range(len(figure.symbols)), 0)

    for wire in figure.wires:
        # (t, sembol indeksi): bu telin sembollerle temas ettiği noktalar.
        touches: list[tuple[float, int]] = []
        for index, symbol in enumerate(figure.symbols):
            clipped = _clip_to_rect(wire, symbol.rect, SYMBOL_PAD)
            if clipped is None:
                continue
            t_min, t_max = clipped
            # Telin sembolden gerçekten GEÇMESİ gerekir: yalnızca teğet
            # geçen (sıfır uzunlukta kalan) durum kesme sayılmaz.
            if (t_max - t_min) * wire.length() < 0.5:
                continue
            start_inside = t_min <= 1e-6  # wire.p1 kutunun içinde mi?
            end_inside = t_max >= 1 - 1e-6  # wire.p2 kutunun içinde mi?
            if start_inside and end_inside:
                # Tel baştan sona kutunun içinde — anlamlı bir temas değil.
                continue
            if not start_inside:
                touches.append((t_min, index))
            if not end_inside:
                touches.append((t_max, index))
            touches_per_symbol[index] += (not start_inside) + (not end_inside)

        touches.sort()
        cursor = 0.0
        pending_pin: tuple[int, int] | None = None
        i = 0
        while i < len(touches):
            t, symbol_index = touches[i]
            if i + 1 < len(touches) and touches[i + 1][1] == symbol_index:
                # Bu telin AYNI sembolden iki temas noktası var: tel sembolün
                # içinden GEÇİYOR. Aradaki kısım sembolün kendi gövdesidir
                # (görünürde tel gibi dursa da ayrı bir iletken parça değildir)
                # — eskiden olduğu gibi atlanır, iki ucu ayrı düğüm kalır.
                t_enter, t_exit = t, touches[i + 1][0]
                piece = _Fragment(Wire(wire.point_at(cursor), wire.point_at(t_enter)))
                if pending_pin is not None:
                    piece.pins.append(pending_pin)
                piece.pins.append((symbol_index, 0))
                fragments.append(piece)
                pin_positions[(symbol_index, 0)] = wire.point_at(t_enter)
                pin_positions[(symbol_index, 1)] = wire.point_at(t_exit)
                cursor = t_exit
                pending_pin = (symbol_index, 1)
                i += 2
            else:
                # Tek temas: tel bu sembole yalnızca bir taraftan değip
                # sınırda bitiyor — öbür ucu (varsa) başka bir telden gelecek.
                pin_slot = 0 if (symbol_index, 0) not in pin_positions else 1
                piece = _Fragment(Wire(wire.point_at(cursor), wire.point_at(t)))
                if pending_pin is not None:
                    piece.pins.append(pending_pin)
                piece.pins.append((symbol_index, pin_slot))
                fragments.append(piece)
                pin_positions[(symbol_index, pin_slot)] = wire.point_at(t)
                cursor = t
                pending_pin = (symbol_index, pin_slot)
                i += 1

        tail = _Fragment(Wire(wire.point_at(cursor), wire.p2))
        if pending_pin is not None:
            tail.pins.append(pending_pin)
        fragments.append(tail)

    for index, count in touches_per_symbol.items():
        symbol = figure.symbols[index]
        if count == 0:
            raise SchematicError(
                f"{symbol.kind} sembolü ({symbol.center()[0]:.1f}, {symbol.center()[1]:.1f}) "
                "hiçbir telin üzerinde değil — şekil eksik okundu"
            )
        if count == 1:
            raise SchematicError(
                f"{symbol.kind} sembolü ({symbol.center()[0]:.1f}, {symbol.center()[1]:.1f}) "
                "yalnızca bir ucundan bir tele değiyor — öbür ucu boşta kalmış"
            )
        if count > 2:
            raise SchematicError(
                f"{symbol.kind} sembolü ({symbol.center()[0]:.1f}, {symbol.center()[1]:.1f}) "
                f"{count} kez telle temas ediyor — bağlantısı belirsiz"
            )
    return fragments, pin_positions


def _merge_fragments(
    fragments: list[_Fragment],
    dots: list[tuple[float, float]],
    links: list[Wire] = (),
) -> _DisjointSet:
    """Değen parçaları aynı düğümde birleştirir (şematik bağlantı kuralları)."""
    groups = _DisjointSet(len(fragments))
    for i, first in enumerate(fragments):
        for j in range(i + 1, len(fragments)):
            second = fragments[j]
            if _fragments_connected(first.wire, second.wire, dots):
                groups.union(i, j)

    # Bağlar yalnızca kendi iki ucundaki parçaları birleştirir; yol boyunca
    # hiçbir şeye değmezler.
    for link in links:
        touching = [
            index
            for index, fragment in enumerate(fragments)
            if _distance_to_segment(link.p1, fragment.wire) <= POINT_TOLERANCE
            or _distance_to_segment(link.p2, fragment.wire) <= POINT_TOLERANCE
        ]
        for index in touching[1:]:
            groups.union(touching[0], index)
    return groups


def _touch_on_wire(point: tuple[float, float], wire: Wire) -> tuple[float, bool]:
    """(mesafe, iç_nokta_mi). `iç_nokta_mi` True ise nokta `wire`nin ORTASINA
    (bir T birleşimi), False ise `wire`nin kendi UCUNA yakın düşüyor demektir.
    """
    (x0, y0), (x1, y1) = wire.p1, wire.p2
    dx, dy = x1 - x0, y1 - y0
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return math.dist(point, wire.p1), False
    t = ((point[0] - x0) * dx + (point[1] - y0) * dy) / denominator
    t_clamped = max(0.0, min(1.0, t))
    distance = math.dist(point, (x0 + t_clamped * dx, y0 + t_clamped * dy))
    return distance, 0.05 < t_clamped < 0.95


def _fragments_connected(a: Wire, b: Wire, dots: list[tuple[float, float]]) -> bool:
    # Uç uca ya da T birleşimi: bir parçanın UCU diğerine değiyor. UÇ UCA
    # temas SIKI toleransla ölçülür: iki BAĞIMSIZ çizilmiş ucun rastgele
    # birbirine yakın düşmesi mümkün (ölçüldü: Figure 7.43'te anahtarın
    # gövde teli, B kontağının teline 0.49pt kadar yaklaşıyor ama aralarında
    # GÖRÜNÜR boşluk var — geniş toleransla yanlışlıkla birleştiriliyordu).
    # T birleşimi (ucun ötekinin ORTASINA değmesi) çok daha az tesadüfi
    # olabilir — bir noktanın rastgele tam bir doğru parçasının üzerine
    # denk gelmesi gerekir — bu yüzden daha geniş toleransla kalır.
    for point in (a.p1, a.p2):
        distance, interior = _touch_on_wire(point, b)
        if distance <= (POINT_TOLERANCE if interior else ENDPOINT_JOIN_TOLERANCE):
            return True
    for point in (b.p1, b.p2):
        distance, interior = _touch_on_wire(point, a)
        if distance <= (POINT_TOLERANCE if interior else ENDPOINT_JOIN_TOLERANCE):
            return True
    # Ortadan kesişme: YALNIZCA birleşim noktası (dolu daire) varsa bağlı.
    crossing = _crossing_point(a, b)
    if crossing is not None:
        return any(math.dist(crossing, dot) <= POINT_TOLERANCE * 2 for dot in dots)
    return False


# --- etiket eşleştirme -----------------------------------------------------


def assign_values(symbols: list[Symbol], labels: list[Label]) -> list[Symbol]:
    """Sayısal etiketleri sembollere en yakınlık sırasına göre dağıtır.

    Açgözlü ve KÜRESEL: tüm (sembol, etiket) çiftleri uzaklığa göre
    sıralanır, en yakın eşleşme önce bağlanır ve her ikisi de listeden
    düşer. Böylece iki sembole eşit yakınlıktaki bir etiket ikisine birden
    verilmez — sırayla eşleştirmenin sessiz hatası budur.

    Yalnızca BİRİMİ uyan çiftler eşleştirilir (bkz. `UNIT_KINDS`).
    """
    numeric = [label for label in labels if label.value is not None]
    pairs = sorted(
        (
            (math.dist(symbol.center(), label.center), symbol_index, label_index)
            for symbol_index, symbol in enumerate(symbols)
            if symbol.value is None
            for label_index, label in enumerate(numeric)
            if label.unit is None or UNIT_KINDS.get(label.unit) == symbol.kind
        ),
        key=lambda item: item[0],
    )
    used_symbols: set[int] = set()
    used_labels: set[int] = set()
    resolved = list(symbols)
    for _, symbol_index, label_index in pairs:
        if symbol_index in used_symbols or label_index in used_labels:
            continue
        symbol = resolved[symbol_index]
        resolved[symbol_index] = Symbol(
            kind=symbol.kind,
            rect=symbol.rect,
            value=numeric[label_index].value,
            name=symbol.name,
            orientation=symbol.orientation,
            control_ref=symbol.control_ref,
            probe_key=symbol.probe_key,
            probe_is_current=symbol.probe_is_current,
        )
        used_symbols.add(symbol_index)
        used_labels.add(label_index)
    return resolved


# --- ana giriş noktası -----------------------------------------------------


_KIND_PREFIX = {
    "resistor": "R",
    "voltage_source": "V",
    "current_source": "I",
    "capacitor": "C",
    "inductor": "L",
    "vcvs": "E",
    "ccvs": "H",
}


def _flipped(
    symbol: Symbol,
    pin_positions: dict[tuple[int, int], tuple[float, float]],
    symbol_index: int,
) -> bool:
    """Uç 1, sembolün `orientation` yönüne uç 0'dan daha mı yakın?

    Öyleyse uçlar ters sırada demektir ve `nodes` çevrilmelidir. Kaynaklarda
    bu sıra ANLAM taşır: gerilim kaynağında `nodes[0]` artı uçtur, ters
    yazılırsa devre doğru çözülür ama işaretler baştan sona ters çıkar.
    """
    centre = symbol.center()
    direction_x, direction_y = symbol.orientation
    projections = []
    for pin in (0, 1):
        point = pin_positions.get((symbol_index, pin))
        if point is None:
            return False
        projections.append(
            (point[0] - centre[0]) * direction_x + (point[1] - centre[1]) * direction_y
        )
    return projections[1] > projections[0]


def build_netlist(figure: Figure) -> tuple[Netlist, dict[str, str]]:
    """Şekil geometrisinden netlist üretir.

    Dönen: (netlist, terminal_adlari) — `terminal_adlari` şekildeki açık
    uçların (küçük boş daireler) hangi düğüme denk geldiğini verir; eşdeğer
    direnç bu iki uç arasında sorulur.
    """
    if not figure.symbols:
        raise SchematicError("Şekilde eleman sembolü bulunamadı")
    if not figure.wires:
        raise SchematicError("Şekilde tel bulunamadı")

    symbols = assign_values(figure.symbols, figure.labels)
    wires = join_hops(figure.wires)
    fragments, pin_positions = _split_wires(
        Figure(wires=wires, symbols=symbols, dots=figure.dots)
    )
    groups = _merge_fragments(fragments, figure.dots, chain_links(figure.links))

    # Her sembol ucunun hangi düğüme düştüğü.
    pin_nodes: dict[tuple[int, int], int] = {}
    for index, fragment in enumerate(fragments):
        for pin in fragment.pins:
            pin_nodes[pin] = groups.find(index)

    # Düğümlere okunabilir ad: yukarıdan aşağı, soldan sağa sırayla n1, n2...
    root_positions: dict[int, tuple[float, float]] = {}
    for index, fragment in enumerate(fragments):
        root = groups.find(index)
        centre = fragment.wire.point_at(0.5)
        current = root_positions.get(root)
        if current is None or (centre[1], centre[0]) < (current[1], current[0]):
            root_positions[root] = centre
    # Toprak sembolünün değdiği düğüm "gnd" olur — çözücünün istediği
    # referans düğüm bu. Birden fazla toprak sembolü aynı düğümü gösterir
    # (şematik kuralı), bu yüzden hepsinin aynı ada gelmesi doğrudur.
    grounded: set[int] = set()
    for point in figure.grounds:
        for index, fragment in enumerate(fragments):
            if _distance_to_segment(point, fragment.wire) <= GROUND_SNAP:
                grounded.add(groups.find(index))
                break

    node_names: dict[int, str] = dict.fromkeys(grounded, "gnd")
    ordered_roots = sorted(root_positions.items(), key=lambda item: (item[1][1], item[1][0]))
    counter = 0
    for root, _ in ordered_roots:
        if root in node_names:
            continue
        counter += 1
        node_names[root] = f"n{counter}"

    elements: list[Element] = []
    counters: dict[str, int] = {}
    # Bağımlı kaynaklar İKİNCİ geçişte kurulur: kontrol büyüklüğünün
    # SAĞLAYICISI olan elemanın (genelde bir direnç) kendi düğümlerine ya da
    # adına bakar, ve o eleman figürde bağımlı kaynaktan SONRA gelebilir.
    # `probe_providers` — GERİLİM problarının (VCVS için) yön-çözümlenmiş
    # (+, −) düğüm çiftini; `current_probe_providers` — AKIM problarının
    # (CCVS için) sağlayıcı elemanın ADINI tutar.
    probe_providers: dict[str, tuple[str, str]] = {}
    current_probe_providers: dict[str, str] = {}
    pending_controlled: list[tuple[str, str, str, float | None, str]] = []
    ordered = sorted(range(len(symbols)), key=lambda i: (symbols[i].center()[1], symbols[i].center()[0]))
    for symbol_index in ordered:
        symbol = symbols[symbol_index]
        first = pin_nodes.get((symbol_index, 0))
        second = pin_nodes.get((symbol_index, 1))
        if first is None or second is None:
            raise SchematicError(f"{symbol.kind} sembolünün bir ucu hiçbir düğüme bağlanmadı")
        if first == second:
            # Not: bu HER ZAMAN okuma hatası değildir — kitapta kasıtlı kısa
            # devre gösteren anlatım şekilleri var (örn. Fig 2.33'te "R2 = 0").
            # Yine de netlist'e çevrilemez, o yüzden ayırt edilebilir bir
            # hata veriyoruz.
            raise SchematicError(
                f"{symbol.kind} sembolünün iki ucu aynı düğümde (kısa devre): şekilde "
                "bilerek kısa devre olabilir ya da bir tel yanlış okunmuş olabilir"
            )
        if symbol.orientation is not None and _flipped(symbol, pin_positions, symbol_index):
            first, second = second, first
        resolved_nodes = (node_names[first], node_names[second])
        prefix = _KIND_PREFIX[symbol.kind]
        counters[prefix] = counters.get(prefix, 0) + 1
        name = symbol.name or f"{prefix}{counters[prefix]}"

        if symbol.probe_key is not None:
            if symbol.probe_is_current:
                current_probe_providers[symbol.probe_key] = name
            else:
                probe_providers[symbol.probe_key] = resolved_nodes

        if symbol.control_ref is not None:
            pending_controlled.append((name, symbol.kind, resolved_nodes, symbol.value, symbol.control_ref))
            continue
        elements.append(
            Element(name=name, kind=symbol.kind, nodes=resolved_nodes, value=symbol.value)
        )

    for name, kind, nodes, value, control_ref in pending_controlled:
        if kind == "ccvs":
            if control_ref not in current_probe_providers:
                raise SchematicError(
                    f"{name}: kontrol akımı {control_ref!r} şekilde hiçbir elemanın "
                    "yanında oklu işaretli değil (eşleşen akım prob etiketi bulunamadı)"
                )
            elements.append(
                Element(
                    name=name,
                    kind=kind,
                    nodes=nodes,
                    value=value,
                    control_element=current_probe_providers[control_ref],
                )
            )
            continue
        if control_ref not in probe_providers:
            raise SchematicError(
                f"{name}: kontrol değişkeni {control_ref!r} şekilde hiçbir elemanın "
                "yanında işaretli değil (eşleşen '+/- ' etiketi bulunamadı)"
            )
        elements.append(
            Element(name=name, kind=kind, nodes=nodes, value=value, control_nodes=probe_providers[control_ref])
        )

    terminals: dict[str, str] = {}
    for order, terminal in enumerate(figure.terminals, start=1):
        label = terminal.name or f"t{order}"
        for index, fragment in enumerate(fragments):
            if _distance_to_segment(terminal.point, fragment.wire) <= POINT_TOLERANCE * 3:
                terminals[label] = node_names[groups.find(index)]
                break

    return Netlist(elements), terminals


# --- anahtarlı (switch) devreler: TEK çizimden İKİ netlist ----------------


def build_switch_netlists(figure: Figure) -> tuple[Netlist, dict[str, str], Netlist, dict[str, str]]:
    """Anahtarlı bir şekilden `(before, before_terminals, after, after_terminals)` üretir.

    Kitabın çizim kuralı: kör (blade), ortak uçtan şu anki (t<0) kontağa
    çizilir; öbür kontak yalnızca dairesiyle (ve harfiyle: "A", "B") durur.
    Bu fonksiyon köre bakıp hangi kontağın "şu an" hangisinin "sonra"
    olduğunu ayırt eder — çağıran taraf hangisinin before/after olduğuna
    dair BİR ŞEY UYDURMAZ, doğrudan çizimden okur.

    "Önce" netlist'i: kör OLDUĞU GİBİ bırakılır (gerçek çizim, ekstra
    varsayım yok). "Sonra" netlist'i: kör, DİĞER kontağa taşınmış gibi
    kurulur — kör çizgisinin `p1` ucu kitapta HER ZAMAN şu an dokunulan
    kontağın ÜZERİNE çizilir (ölçüldü: Figure 7.43, blade.p1 ile A
    arası 0.09 pt — pratikte aynı nokta), `p2` ucu ise ORTAK/pivot
    noktasıdır ve anahtar konumu değişse de YERİNDE KALIR. Bu yüzden
    "şu an" hangi kontak diye `p1`'e en yakın olana, "sonra" da ötekine
    bakılır — `p2`'ye bakmak yanlış sonuç verir (pivot ikisine de
    yaklaşık eşit uzaklıkta durabilir).
    """
    if figure.switch_blade is None:
        raise SchematicError("Bu şekilde anahtar (switch) körü bulunamadı")
    blade = figure.switch_blade

    if len(figure.terminals) < 2:
        raise SchematicError(
            f"Anahtarın iki kontağı (ör. 'A', 'B') bulunamadı: {len(figure.terminals)} uç var"
        )
    ordered = sorted(figure.terminals, key=lambda t: math.dist(blade.p1, t.point))
    contact_other = ordered[1]

    base = Figure(
        wires=figure.wires,
        symbols=figure.symbols,
        dots=figure.dots,
        terminals=[],
        labels=figure.labels,
        grounds=figure.grounds,
        links=figure.links,
    )
    before_figure = Figure(
        wires=[*base.wires, blade], symbols=base.symbols, dots=base.dots,
        terminals=base.terminals, labels=base.labels, grounds=base.grounds, links=base.links,
    )
    after_figure = Figure(
        wires=[*base.wires, Wire(blade.p2, contact_other.point)], symbols=base.symbols,
        dots=base.dots, terminals=base.terminals, labels=base.labels, grounds=base.grounds,
        links=base.links,
    )
    before_netlist, before_terminals = build_netlist(before_figure)
    after_netlist, after_terminals = build_netlist(after_figure)
    return before_netlist, before_terminals, after_netlist, after_terminals
