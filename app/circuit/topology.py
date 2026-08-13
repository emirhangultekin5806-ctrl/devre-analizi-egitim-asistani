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
"""

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


def reduce_resistors(
    netlist: Netlist, protected_nodes: tuple[str, ...] = ()
) -> tuple[Netlist, list[ReductionStep]]:
    """Devreyi seri/paralel kurallarıyla indirger; adımları da döndürür.

    Kaynaklar (voltage_source/current_source) indirgemeye katılmaz, yerinde
    kalır — seri tespiti yalnızca iki DİRENCİN paylaştığı düğümlerde çalışır,
    böylece kaynağın olduğu düğüm yanlışlıkla birleştirilmez.

    Tüm devreler seri/paralel ile indirgenemez (örn. köprü/Wheatstone) —
    o durumda indirgenebildiği yere kadar gider ve kalan netlist'i döndürür.
    Çağıran taraf `len(result.elements)` bakarak tam indirgenip
    indirgenmediğini anlayabilir.
    """
    elements = list(netlist.elements)
    steps: list[ReductionStep] = []
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
