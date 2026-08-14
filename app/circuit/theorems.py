"""Süperpozisyon ve Thevenin/Norton eşdeğerleri — Sadiku Bölüm 4.

Bu modül yeni bir çözüm yöntemi İCAT ETMİYOR: her ikisi de `solve_dc`'yi
tekrar tekrar, farklı biçimde "budanmış" netlist'lerle çağırıyor. Kitabın
kendi tanımı birebir kodda:

- **Süperpozisyon**: her BAĞIMSIZ kaynak tek başına aktifken (diğerleri
  "öldürülmüş" — gerilim kaynağı kısa devre, akım kaynağı açık devre)
  hedef elemanın tepkisi hesaplanır; toplamları gerçek (tüm kaynaklar
  aktif) sonuca eşit olmalıdır — bu eşitlik `superposition()` içinde
  bağımsız bir tutarlılık kontrolü olarak DOĞRULANIR, varsayılmaz.
- **Thevenin/Norton**: `R_th` bulunurken bağımsız kaynaklar öldürülüp
  uçlara 1 A'lık bir test kaynağı enjekte edilir (Sadiku'nun kendi
  belirttiği alternatif yöntem — bkz. Example 4.9 metni: "we may insert
  a current source... at terminals a-b"). Bu yöntem `topology.py`'nin
  seri/paralel/Y-Δ indirgemesinden daha GENELDİR: devrede bağımlı kaynak
  olsa bile çalışır (bağımlı kaynaklar bu süreçte ASLA öldürülmez —
  kitabın kendi uyarısı: "dependent sources are not to be turned off
  because they are controlled by circuit variables").

Doğrulama (gerçek kitap örnekleri, `tests/test_circuit_theorems.py`):
  - Example 4.3: süperpozisyon toplamı v=2+8=10V, kitapla birebir.
  - Example 4.9 (Figure 4.28): V_th=30V, R_th=4Ω, kitapla birebir.
"""

from dataclasses import dataclass

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import SolverError, element_results, solve_dc

_INDEPENDENT_KINDS = {"voltage_source", "current_source"}


def kill_independent_sources(netlist: Netlist) -> Netlist:
    """Bağımsız kaynakları öldürür: gerilim kaynağı → 0 V (kısa devre),
    akım kaynağı → 0 A (açık devre). BAĞIMLI kaynaklara (vcvs, ccvs)
    dokunulmaz — kontrol değişkenleri devrenin geri kalanından geldiği
    için "öldürme" kavramı onlara uygulanmaz (kitabın kendi uyarısı,
    modül docstring'inde alıntılandı).
    """
    killed = []
    for element in netlist.elements:
        if element.kind in _INDEPENDENT_KINDS:
            killed.append(Element(element.name, element.kind, element.nodes, 0.0))
        else:
            killed.append(element)
    return Netlist(killed)


def _unused_name(netlist: Netlist, base: str) -> str:
    existing = {element.name for element in netlist.elements}
    if base not in existing:
        return base
    counter = 1
    while f"{base}{counter}" in existing:
        counter += 1
    return f"{base}{counter}"


@dataclass(frozen=True)
class SuperpositionTerm:
    """Tek bir bağımsız kaynağın hedef eleman üzerindeki TEK BAŞINA katkısı."""

    source_name: str
    voltage: float
    current: float

    def describe(self) -> str:
        return f"{self.source_name} tek başına: V = {self.voltage:.4g} V, I = {self.current:.4g} A"


@dataclass(frozen=True)
class SuperpositionResult:
    """`superposition()`'ın tam sonucu: katkılar + toplam + gerçek değerle karşılaştırma."""

    element_name: str
    terms: list[SuperpositionTerm]
    total_voltage: float
    total_current: float
    actual_voltage: float
    actual_current: float

    def matches_actual(self, tolerance: float = 1e-6) -> bool:
        """Katkıların toplamı, TÜM kaynaklar aktifken hesaplanan gerçek
        değere eşit mi? Süperpozisyonun matematiksel garantisi bu —
        tutmuyorsa `kill_independent_sources` ya da hesap hatalıdır."""
        return (
            abs(self.total_voltage - self.actual_voltage) <= tolerance
            and abs(self.total_current - self.actual_current) <= tolerance
        )

    def describe(self) -> list[str]:
        lines = [term.describe() for term in self.terms]
        lines.append(
            f"Toplam: V = {self.total_voltage:.4g} V, I = {self.total_current:.4g} A"
        )
        return lines


def superposition(
    netlist: Netlist, element_name: str, reference: str | None = None
) -> SuperpositionResult:
    """Her bağımsız kaynağın `element_name` üzerindeki katkısını ayrı ayrı bulur.

    En az 2 bağımsız kaynak gerektirir — süperpozisyonun anlamlı olması için
    "diğer kaynaklar" diye bir şey olmalı.
    """
    independent = [e for e in netlist.elements if e.kind in _INDEPENDENT_KINDS]
    if len(independent) < 2:
        raise SolverError(
            f"Süperpozisyon en az 2 bağımsız kaynak gerektirir, devrede {len(independent)} var"
        )

    terms = []
    for source in independent:
        elements = []
        for element in netlist.elements:
            if element.name == source.name:
                elements.append(element)  # bu kaynak aktif kalır
            elif element.kind in _INDEPENDENT_KINDS:
                elements.append(Element(element.name, element.kind, element.nodes, 0.0))
            else:
                elements.append(element)
        sub_netlist = Netlist(elements)
        results = element_results(sub_netlist, solve_dc(sub_netlist, reference=reference))
        if element_name not in results:
            raise SolverError(f"{element_name!r} adlı eleman netlist'te yok")
        target = results[element_name]
        terms.append(SuperpositionTerm(source.name, target.voltage, target.current))

    actual = element_results(netlist, solve_dc(netlist, reference=reference))[element_name]
    return SuperpositionResult(
        element_name=element_name,
        terms=terms,
        total_voltage=sum(term.voltage for term in terms),
        total_current=sum(term.current for term in terms),
        actual_voltage=actual.voltage,
        actual_current=actual.current,
    )


@dataclass(frozen=True)
class TheveninResult:
    """a-b uçlarındaki Thevenin (V_th, R_th) ve Norton (I_N) eşdeğeri."""

    terminal_a: str
    terminal_b: str
    v_th: float
    r_th: float

    @property
    def i_norton(self) -> float:
        """I_N = V_th / R_th (Norton akım kaynağı, R_th ile paralel)."""
        if self.r_th == 0:
            raise SolverError("R_th = 0: Norton akımı tanımsız (ideal kısa devre)")
        return self.v_th / self.r_th

    def describe(self) -> str:
        return (
            f"V_th({self.terminal_a},{self.terminal_b}) = {self.v_th:.4g} V, "
            f"R_th = {self.r_th:.4g} Ω, I_N = {self.i_norton:.4g} A"
        )


def thevenin_resistance(
    netlist: Netlist, terminal_a: str, terminal_b: str, reference: str | None = None
) -> float:
    """Yalnızca R_th — bağımsız kaynaklar öldürülüp uçlara 1 A'lık bir test
    akım kaynağı enjekte edilerek ölçülür (bkz. `thevenin_equivalent`
    docstring'i). `thevenin_equivalent`'ten AYRI tutulması bilinçli: V_th
    hesabı devrede en az bir bağımsız kaynak gerektirir, ama R_th
    KAYNAKSIZ bir devrede de (örn. `transient.py`'deki source-free RLC
    zaman sabiti hesabında) anlamlıdır — bu fonksiyon o durumda da çalışır.
    """
    killed = kill_independent_sources(netlist)
    probe_name = _unused_name(killed, "Ith")
    # 1 A, terminal_b'den terminal_a'ya (b=- terminali, a=+ terminali):
    # boylece V(a)-V(b) dogrudan R_th'e esit cikiyor (elle dogrulandi,
    # Example 4.9 — bkz. modul docstring'i).
    probe = Element(probe_name, "current_source", (terminal_b, terminal_a), 1.0)
    test_netlist = Netlist([*killed.elements, probe])
    return solve_dc(test_netlist, reference=reference).voltage_across(terminal_a, terminal_b)


def thevenin_equivalent(
    netlist: Netlist, terminal_a: str, terminal_b: str, reference: str | None = None
) -> TheveninResult:
    """`terminal_a`-`terminal_b` arasındaki Thevenin/Norton eşdeğerini bulur.

    V_th: uçlar AÇIK iken aralarındaki gerilim (devre olduğu gibi, tüm
    kaynaklar aktif — Thevenin geriliminin tanımı budur, yük BAĞLANMAMIŞ
    haldeki açık devre gerilimidir). Bu adım en az bir bağımsız kaynak
    gerektirir; kaynaksız bir devrede yalnızca R_th isteniyorsa
    `thevenin_resistance` kullanılmalı.

    R_th: bağımsız kaynaklar öldürülüp uçlara 1 A'lık bir test akım
    kaynağı enjekte edilerek ölçülür — devrede bağımlı kaynak olsa da
    doğru sonuç verir.
    """
    v_th = solve_dc(netlist, reference=reference).voltage_across(terminal_a, terminal_b)
    r_th = thevenin_resistance(netlist, terminal_a, terminal_b, reference)
    return TheveninResult(terminal_a=terminal_a, terminal_b=terminal_b, v_th=v_th, r_th=r_th)
