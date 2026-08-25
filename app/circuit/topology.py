"""Seri/paralel tespiti ve adım adım indirgeme — tamamen deterministik.

Burada model, tahmin veya LLM YOKTUR. Netlist doğruysa sonuç kesindir;
netlist yanlışsa sonuç da yanlış olur (çöp girdi, çöp çıktı) — bu yüzden
asıl doğrulama netlist üzerinde yapılmalı (bkz. `netlist.py` docstring'i).

Tanımlar (ders kitabı tanımlarının birebir karşılığı):

- **Seri:** iki eleman bir düğümü paylaşır ve o düğüme BAŞKA eleman bağlı
  değildir (düğüm derecesi tam 2). "Aradan başka bir kol çıkmıyorsa seridir"
  ifadesinin kesin hali budur.
- **Paralel:** iki eleman HER İKİ düğümü de paylaşır.

`reduce_resistors` bu iki kuralı tekrar tekrar uygulayarak devreyi tek bir
eşdeğer dirence indirger ve her adımı kaydeder — öğrenci indirgemenin
sırasını görebilsin diye (ders kitabındaki çözüm yöntemi de budur).

Bazı devreler (köprü/Wheatstone gibi) yalnızca seri/paralel ile
indirgenemez — ders kitabı (Sadiku §2.7) bu durumda **yıldız-üçgen
(Y-Δ) dönüşümü** kullanır: üç direncin buluştuğu bir düğüm (yıldız
merkezi) kaldırılıp, dış üç düğüm arasına eşdeğer bir üçgen konur. Bu,
önceden paralel OLMAYAN direnç çiftlerini paralel hale getirir ve
indirgeme devam edebilir. `reduce_resistors` seri/paralel tükendiğinde
otomatik olarak bunu dener (bkz. Sadiku Example 2.15, aşağıda test
edilen köprü devresi).
"""

import cmath
import math
from dataclasses import dataclass

from app.circuit.netlist import Element, Netlist


@dataclass(frozen=True)
class ReductionStep:
    """Tek bir indirgeme adımı (öğrenciye gösterilecek)."""

    kind: str  # "seri" | "paralel"
    combined: tuple[str, ...]  # birleştirilen eleman adları
    result_name: str
    result_value: float

    def describe(self) -> str:
        parts = " + ".join(self.combined) if self.kind == "seri" else " ∥ ".join(self.combined)
        return f"{parts} ({self.kind}) → {self.result_name} = {self.result_value:g} Ω"


def find_series_pair(
    netlist: Netlist, protected_nodes: tuple[str, ...] = ()
) -> tuple[Element, Element, str] | None:
    """Seri bağlı ilk direnç çiftini ve paylaştıkları düğümü döndürür.

    Koşul: ortak düğümün derecesi tam 2 (o düğüme başka eleman bağlı değil).

    `protected_nodes` — devrenin dış UÇLARI. Bir uç düğümde birleştirme
    yapılmamalı: eşdeğer direnç a-b arasında sorulduğunda a'ya bağlı iki
    direnç "seri" değildir, oradan devreye giren iki ayrı koldur. Bu
    korunmazsa köprü (Wheatstone) gibi indirgenemez devreler sessizce ve
    yanlış biçimde indirgenir.
    """
    for node in sorted(netlist.nodes()):
        if node in protected_nodes:
            continue
        attached = netlist.elements_at(node)
        if len(attached) != 2:
            continue
        first, second = attached
        if first.kind == "resistor" and second.kind == "resistor":
            return first, second, node
    return None


def find_parallel_pair(netlist: Netlist) -> tuple[Element, Element] | None:
    """Paralel bağlı ilk direnç çiftini döndürür (iki düğümü de ortak)."""
    resistors = [e for e in netlist.elements if e.kind == "resistor"]
    for i, first in enumerate(resistors):
        for second in resistors[i + 1 :]:
            if set(first.nodes) == set(second.nodes):
                return first, second
    return None


def _series_value(first: Element, second: Element) -> float:
    return first.value + second.value


def _parallel_value(first: Element, second: Element) -> float:
    return (first.value * second.value) / (first.value + second.value)


# --- yıldız-üçgen (Y-Δ) dönüşümü --------------------------------------------


@dataclass(frozen=True)
class WyeDeltaStep:
    """Yıldız (Y) → üçgen (Δ) dönüşüm adımı — 3 direnç 3 direnç ile değişir.

    Seri/paralel adımlarından (`ReductionStep`) farklı bir şekli var (tek
    sonuç yerine üç), bu yüzden ayrı bir tür: `reduce_resistors`'ın adım
    listesi ikisini de içerebilir.
    """

    center_node: str
    combined: tuple[str, str, str]
    results: tuple[str, str, str]
    result_values: tuple[float, float, float]

    def describe(self) -> str:
        old = " + ".join(self.combined)
        new = ", ".join(
            f"{name}={value:g} Ω"
            for name, value in zip(self.results, self.result_values, strict=True)
        )
        return f"{old} (yıldız→üçgen, merkez={self.center_node}) → {new}"


def delta_to_wye(r_ab: float, r_bc: float, r_ca: float) -> tuple[float, float, float]:
    """Δ (a-b-c üçgeni) → Y (merkez n). Döner: (Ra, Rb, Rc) — n'den a/b/c'ye.

    Sadiku Eq. (2.49)-(2.51); Example 2.14 ile doğrulandı:
    Rab=10, Rbc=25, Rca=15 → {Ra,Rb,Rc}={3, 5, 7.5} (kitapla birebir).
    """
    total = r_ab + r_bc + r_ca
    r_a = (r_ab * r_ca) / total
    r_b = (r_ab * r_bc) / total
    r_c = (r_bc * r_ca) / total
    return r_a, r_b, r_c


def wye_to_delta(r_a: float, r_b: float, r_c: float) -> tuple[float, float, float]:
    """Y (merkez n, kollar a/b/c'ye) → Δ (a-b-c üçgeni). Döner: (Rab, Rbc, Rca).

    Sadiku Eq. (2.52) ve devamı; Practice Problem 2.14 ile doğrulandı:
    Ra=10, Rb=20, Rc=40 → {Rab,Rbc,Rca}={140, 70, 35} (kitapla birebir).
    """
    sum_products = r_a * r_b + r_b * r_c + r_c * r_a
    r_ab = sum_products / r_c
    r_bc = sum_products / r_a
    r_ca = sum_products / r_b
    return r_ab, r_bc, r_ca


def find_wye_center(netlist: Netlist, protected_nodes: tuple[str, ...] = ()) -> str | None:
    """Tam olarak 3 dirence bağlı, korumasız ilk düğümü (yıldız merkezi adayı) bulur.

    `protected_nodes` — devrenin dış uçları (seri tespitindeki gerekçenin
    aynısı): bir uç düğüm 3 dirence bağlı olsa bile yıldız merkezi olarak
    kaldırılamaz, çünkü dışarıdan oraya bağlanan bir ölçüm noktasıdır.
    """
    for node in sorted(netlist.nodes()):
        if node in protected_nodes:
            continue
        attached = netlist.elements_at(node)
        if len(attached) == 3 and all(e.kind == "resistor" for e in attached):
            return node
    return None


def transform_wye_to_delta(
    netlist: Netlist, center: str, counter: int
) -> tuple[Netlist, WyeDeltaStep]:
    """Verilen merkezdeki yıldızı üçgene çevirir; merkez düğüm devreden kalkar.

    Dış üç düğüm arasına konan üç yeni direnç, o düğüm çiftleri arasında
    ZATEN bir direnç varsa onunla PARALEL olur — `reduce_resistors`'ın bir
    sonraki turu bunu yakalar. Bu, bir köprü (Wheatstone) devresinin
    seri/paralel ile indirgenemeyen tıkanıklığını açan asıl mekanizmadır.
    """
    star = netlist.elements_at(center)
    if len(star) != 3 or any(e.kind != "resistor" for e in star):
        raise ValueError(f"{center!r} tam olarak 3 dirence bağlı bir yıldız merkezi değil")

    outer_of = {element.name: element.other_node(center) for element in star}
    (name_a, r_a), (name_b, r_b), (name_c, r_c) = (
        (element.name, element.value) for element in star
    )
    node_a, node_b, node_c = outer_of[name_a], outer_of[name_b], outer_of[name_c]

    r_ab, r_bc, r_ca = wye_to_delta(r_a, r_b, r_c)
    new_ab = Element(f"Rd{counter}", "resistor", (node_a, node_b), r_ab)
    new_bc = Element(f"Rd{counter + 1}", "resistor", (node_b, node_c), r_bc)
    new_ca = Element(f"Rd{counter + 2}", "resistor", (node_c, node_a), r_ca)

    remaining = [e for e in netlist.elements if e.name not in (name_a, name_b, name_c)]
    step = WyeDeltaStep(
        center_node=center,
        combined=(name_a, name_b, name_c),
        results=(new_ab.name, new_bc.name, new_ca.name),
        result_values=(r_ab, r_bc, r_ca),
    )
    return Netlist([*remaining, new_ab, new_bc, new_ca]), step


def reduce_resistors(
    netlist: Netlist, protected_nodes: tuple[str, ...] = ()
) -> tuple[Netlist, list[ReductionStep | WyeDeltaStep]]:
    """Devreyi seri/paralel/yıldız-üçgen kurallarıyla indirger; adımları da döndürür.

    Kaynaklar (voltage_source/current_source) indirgemeye katılmaz, yerinde
    kalır — seri tespiti yalnızca iki DİRENCİN paylaştığı düğümlerde çalışır,
    böylece kaynağın olduğu düğüm yanlışlıkla birleştirilmez.

    Sıra ÖNEMLİ: önce paralel, sonra seri, en son (ikisi de tıkanınca)
    yıldız-üçgen denenir. Y-Δ dönüşümü zaten indirgenebilecek bir devreye
    gereksiz yere uygulanmasın diye en son sırada — ders kitabının kendi
    yöntemi de bu (Sadiku §2.7: "önce seri/paralel, tıkanırsa Y-Δ").

    Hâlâ indirgenemeyen devreler kalabilir (örn. dengesiz köprüler, ya da
    hiç yıldız/üçgen içermeyen indirgenemez topolojiler) — o durumda
    indirgenebildiği yere kadar gider ve kalan netlist'i döndürür. Çağıran
    taraf `len(result.elements)` bakarak tam indirgenip indirgenmediğini
    anlayabilir.
    """
    elements = list(netlist.elements)
    steps: list[ReductionStep | WyeDeltaStep] = []
    counter = 1

    while True:
        current = Netlist(elements)

        parallel = find_parallel_pair(current)
        if parallel:
            first, second = parallel
            value = _parallel_value(first, second)
            name = f"Rp{counter}"
            steps.append(ReductionStep("paralel", (first.name, second.name), name, value))
            elements = [e for e in elements if e not in (first, second)]
            elements.append(Element(name, "resistor", first.nodes, value))
            counter += 1
            continue

        series = find_series_pair(current, protected_nodes)
        if series:
            first, second, shared = series
            value = _series_value(first, second)
            name = f"Rs{counter}"
            steps.append(ReductionStep("seri", (first.name, second.name), name, value))
            outer = (first.other_node(shared), second.other_node(shared))
            elements = [e for e in elements if e not in (first, second)]
            elements.append(Element(name, "resistor", outer, value))
            counter += 1
            continue

        center = find_wye_center(current, protected_nodes)
        if center:
            new_netlist, step = transform_wye_to_delta(current, center, counter)
            steps.append(step)
            elements = list(new_netlist.elements)
            counter += 3
            continue

        return Netlist(elements), steps


def equivalent_resistance(netlist: Netlist, node_a: str, node_b: str) -> float | None:
    """`node_a`-`node_b` arasındaki eşdeğer direnç; indirgenemezse None.

    Devrede kaynak varsa önce kaynaklar çıkarılmalıdır (Thevenin direnci
    hesabındaki gibi) — bu fonksiyon yalnızca dirençlere bakar.
    """
    resistors = [e for e in netlist.elements if e.kind == "resistor"]
    if not resistors:
        return None
    reduced, _ = reduce_resistors(Netlist(resistors), protected_nodes=(node_a, node_b))
    if len(reduced.elements) != 1:
        return None
    only = reduced.elements[0]
    if set(only.nodes) != {node_a, node_b}:
        return None
    return only.value


def equivalent_impedance(
    netlist: Netlist, node_a: str, node_b: str, omega: float
) -> complex | None:
    """`node_a`-`node_b` arasındaki eşdeğer EMPEDANS (fazör bölgesi); indirgenemezse None.

    Neden ayrı: `equivalent_resistance` yalnızca `resistor` türüne bakar,
    kaynaksız bir AC devresinde (R+L+C ya da "jX Ω" empedans kutuları)
    hiçbir şey indirgenemiyordu — GERÇEK VERİDE ÖLÇÜLDÜ (2026-08-25,
    1-100/14.png, 1-100/48.png, Figure 9.81: üçünde de "Zeq bul" sorusu,
    üçü de "eşdeğer direnç hesaplanamadı" ile reddediliyordu).

    Seri/paralel/Y-Δ kuralları KOMPLEKS empedansta birebir aynıdır (Sadiku
    §9.6), o yüzden aynı indirgeyici yeniden kullanılır: her eleman
    ω'daki empedansına çevrilip sentetik bir "resistor" olarak verilir.

    `omega`: açısal frekans (rad/s). Yalnızca L/C çevriminde kullanılır;
    `impedance` elemanları zaten frekanstan bağımsız verilmiştir.

    LC paralel rezonansında (Z1 + Z2 == 0) eşdeğer sonsuzdur — sayı yerine
    None döner, uydurma bir değer üretilmez.
    """
    as_impedance = []
    for e in netlist.elements:
        if e.kind == "resistor":
            z = complex(e.value, 0.0)
        elif e.kind == "inductor":
            z = complex(0.0, omega * e.value)
        elif e.kind == "capacitor":
            if omega == 0 or e.value == 0:
                return None
            z = complex(0.0, -1.0 / (omega * e.value))
        elif e.kind == "impedance":
            z = cmath.rect(e.value, math.radians(e.phase))
        else:
            return None  # kaynak/bağımlı kaynak varsa bu yol geçerli değil
        if z == 0:
            return None
        as_impedance.append(Element(e.name, "resistor", e.nodes, z))
    if not as_impedance:
        return None
    try:
        reduced, _ = reduce_resistors(Netlist(as_impedance), protected_nodes=(node_a, node_b))
    except ZeroDivisionError:
        return None  # paralel rezonans: eşdeğer sonsuz
    if len(reduced.elements) != 1:
        return None
    only = reduced.elements[0]
    if set(only.nodes) != {node_a, node_b}:
        return None
    return only.value
