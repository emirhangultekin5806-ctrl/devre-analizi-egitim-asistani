"""Devrenin AÇIK gösterimi: hangi eleman hangi iki düğüme bağlı.

Bu modülün varlık sebebi bir hata: bu projede bir devre fotoğrafının
topolojisi "göze bakarak" okunup doğrudan "şu şuna seri" denmiş, ve yanlış
çıkmıştı (kullanıcı düzeltti). Hata seri/paralel kuralında değil, bağlantıyı
görselden çıkarma adımındaydı — ama o adım görünmez olduğu için hata da
görünmez oldu.

Kural şu: bir devre hakkında hiçbir iddia, önce netlist yazılmadan
yapılmaz. Netlist açık, yazılı ve kullanıcıya gösterilebilir olmalı;
öğrenci "R4 ile R5 gerçekten aynı düğüme mi bağlı?" sorusunu resme bakarak
doğrulayabilir — oysa "toplam direnç 10 Ω" iddiasını doğrulayamaz.

Netlist elde olduktan sonra seri/paralel tespiti ve indirgeme tamamen
deterministiktir (bkz. `topology.py`) — orada model/tahmin yoktur.
"""

from dataclasses import dataclass

# Desteklenen eleman türleri. `value` birimi türe göre değişir:
# resistor -> ohm, voltage_source -> volt, current_source -> amper.
ELEMENT_KINDS = {"resistor", "voltage_source", "current_source", "capacitor", "inductor"}


@dataclass(frozen=True)
class Element:
    """İki uçlu bir devre elemanı.

    `nodes` sırası yön taşıyan elemanlar için anlamlıdır (kaynaklarda
    (+, −), diyot benzeri elemanlarda (anot, katot) sırası). Direnç gibi
    yönsüz elemanlarda sıra önemsizdir.
    """

    name: str
    kind: str
    nodes: tuple[str, str]
    value: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in ELEMENT_KINDS:
            raise ValueError(f"Bilinmeyen eleman türü: {self.kind!r}. Secenekler: {sorted(ELEMENT_KINDS)}")
        if len(self.nodes) != 2:
            raise ValueError(f"{self.name}: bir eleman tam olarak 2 düğüme bağlanır, verilen: {self.nodes}")
        if self.nodes[0] == self.nodes[1]:
            raise ValueError(f"{self.name}: iki ucu da aynı düğüme ({self.nodes[0]}) bağlı — kısa devre")

    def other_node(self, node: str) -> str:
        """Verilen düğümün karşısındaki ucu döndürür."""
        if node == self.nodes[0]:
            return self.nodes[1]
        if node == self.nodes[1]:
            return self.nodes[0]
        raise ValueError(f"{self.name} elemanı {node!r} düğümüne bağlı değil")


class Netlist:
    """Bir devrenin eleman listesi + düğüm bağlantıları."""

    def __init__(self, elements: list[Element]) -> None:
        names = [e.name for e in elements]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"Eleman adları benzersiz olmalı, tekrar edenler: {sorted(duplicates)}")
        self.elements = list(elements)

    def __len__(self) -> int:
        return len(self.elements)

    def __repr__(self) -> str:
        return f"Netlist({len(self.elements)} eleman, {len(self.nodes())} düğüm)"

    def nodes(self) -> set[str]:
        return {n for element in self.elements for n in element.nodes}

    def elements_at(self, node: str) -> list[Element]:
        """Bu düğüme bağlı elemanlar."""
        return [e for e in self.elements if node in e.nodes]

    def degree(self, node: str) -> int:
        """Düğüme bağlı eleman sayısı (seri tespitinin temeli)."""
        return len(self.elements_at(node))

    def by_name(self, name: str) -> Element:
        for element in self.elements:
            if element.name == name:
                return element
        raise KeyError(f"{name!r} adlı eleman yok")

    def to_lines(self) -> list[str]:
        """Kullanıcıya gösterilecek okunabilir gösterim.

        Onay adımının temeli: öğrenci bu satırları resimle karşılaştırıp
        "bu bağlantı doğru mu?" diye bakabilir.
        """
        lines = []
        for e in self.elements:
            value = "" if e.value is None else f" = {e.value:g}"
            lines.append(f"{e.name}{value}: {e.nodes[0]}-{e.nodes[1]}")
        return lines

    def dangling_nodes(self) -> list[str]:
        """Yalnızca tek elemana bağlı düğümler — açık uç (muhtemel okuma hatası)."""
        return sorted(n for n in self.nodes() if self.degree(n) == 1)
