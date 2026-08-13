"""Bir topoloji okumasını, kitabın bilinen cevabıyla karşılaştırarak doğrular.

Öz-doğrulama döngüsünün karar mekanizması: sistem devreyi kendi çözer,
sonra sonucu kitabın cevabıyla karşılaştırır. Tutuyorsa okuma doğrulanmış
sayılır ve (görsel → netlist) çifti eğitim verisi olarak kullanılabilir.

**Sıra önemli:** önce çözülür, sonra karşılaştırılır. Cevap çözüme girdi
olarak ASLA verilmez — `app/circuit/problems.py` bunu veri tarafında
yapısal olarak garanti ediyor (soru metni cevabı içeremez).

**Eşleşme kanıt değildir.** Farklı topolojiler aynı sayıyı üretebilir.
Güveni artırmanın yolu birden fazla büyüklüğü birden karşılaştırmaktır;
`verify_netlist` bu yüzden beklenen değerlerin HEPSİNİN karşılanmasını
arar ve kaç bağımsız büyüklüğün tutduğunu raporlar.
"""

from dataclasses import dataclass, field

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import Solution, SolverError, solve_dc, verify_answer

# Birim -> o birimde hangi hesaplanmış büyüklüklere bakılacağı.
_UNIT_KINDS = {"A": "akım", "V": "gerilim", "Ω": "direnç"}


@dataclass
class VerificationResult:
    """Doğrulama sonucu — neyin neden tuttuğu/tutmadığı açıkça görünsün."""

    verified: bool
    matched: tuple[tuple[float, str], ...] = field(default_factory=tuple)
    unmatched: tuple[tuple[float, str], ...] = field(default_factory=tuple)
    computed: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def describe(self) -> str:
        if self.error:
            return f"Doğrulanamadı: {self.error}"
        if self.verified:
            return f"Doğrulandı ({len(self.matched)} değer tuttu)"
        missing = ", ".join(f"{v:g} {u}" for v, u in self.unmatched)
        return f"Tutmadı — beklenen ama bulunamayan: {missing}"


def computed_quantities(netlist: Netlist, solution: Solution) -> dict[str, float]:
    """Çözümden, kitabın cevabıyla karşılaştırılabilecek büyüklükleri toplar.

    Kitap "6 Ω" ya da "1.78 A" der ama hangi düğüm/eleman olduğunu her
    zaman metinde vermez. Bu yüzden tek bir büyüklük seçmek yerine
    hesaplanan tüm adayları toplayıp birim eşleşmesiyle arıyoruz.
    """
    quantities: dict[str, float] = {}

    for name, current in solution.source_currents.items():
        quantities[f"I({name})"] = current
        source = netlist.by_name(name)
        # Kaynaktan görülen eşdeğer direnç (V/I) -- "Req = 6 Ω" tarzı
        # cevaplar bununla karşılaştırılır.
        if source.value and current != 0:
            quantities[f"R_eq({name})"] = abs(source.value / current)

    for node, voltage in solution.node_voltages.items():
        quantities[f"V({node})"] = voltage

    return quantities


def verify_netlist(
    netlist: Netlist,
    expected_values: tuple[tuple[float, str], ...],
    tolerance: float = 0.02,
) -> VerificationResult:
    """Netlist'i çözer ve beklenen değerlerin hepsinin karşılandığını arar.

    `expected_values` — `problems.parse_answer_values` çıktısı: (değer, birim).
    Sayısal cevabı olmayan alıştırmalar (örn. "Answer: Proof.") doğrulanamaz;
    boş liste verilirse sonuç `verified=False` olur, sessizce "başarılı"
    sayılmaz.
    """
    if not expected_values:
        return VerificationResult(False, error="Karşılaştırılacak sayısal cevap yok")

    try:
        solution = solve_dc(netlist)
    except SolverError as exc:
        return VerificationResult(False, error=str(exc))

    quantities = computed_quantities(netlist, solution)

    matched, unmatched = [], []
    for value, unit in expected_values:
        if unit not in _UNIT_KINDS:
            unmatched.append((value, unit))
            continue
        candidates = _candidates_for_unit(quantities, unit)
        if any(verify_answer(candidate, value, tolerance) for candidate in candidates):
            matched.append((value, unit))
        else:
            unmatched.append((value, unit))

    return VerificationResult(
        verified=not unmatched,
        matched=tuple(matched),
        unmatched=tuple(unmatched),
        computed=quantities,
    )


def _candidates_for_unit(quantities: dict[str, float], unit: str) -> list[float]:
    prefix = {"A": "I(", "V": "V(", "Ω": "R_eq("}[unit]
    return [v for name, v in quantities.items() if name.startswith(prefix)]


@dataclass
class MethodAgreement:
    """Aynı devrenin iki FARKLI ÇÖZÜM YÖNTEMİYLE sonuçlarının karşılaştırması.

    Ders kitabının öğrettiği iki temel yöntem:
      - düğüm analizi (KCL tabanlı, bilinmeyen: düğüm gerilimleri) — ngspice
      - çevre analizi (KVL tabanlı, bilinmeyen: çevre akımları) — app/circuit/mesh.py
    Farklı denklem sistemleri kurdukları için uyuşmaları güçlü bir delildir
    ve **kitabın cevabına ihtiyaç duymaz**.
    """

    agree: bool
    nodal: dict[str, float] = field(default_factory=dict)
    mesh: dict[str, float] = field(default_factory=dict)
    disagreements: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

    def describe(self) -> str:
        if self.error:
            return f"Karşılaştırılamadı: {self.error}"
        if self.agree:
            return f"Düğüm ve çevre analizi uyuşuyor ({len(self.nodal)} eleman akımı)"
        return f"UYUŞMUYOR — farklı çıkan elemanlar: {', '.join(self.disagreements)}"


def cross_check_methods(netlist: Netlist, tolerance: float = 1e-6) -> MethodAgreement:
    """Devreyi düğüm ve çevre analiziyle ayrı ayrı çözüp akımları karşılaştırır.

    Bir yöntem uygulanamıyorsa (örn. akım kaynağı çevre analizinde
    süpermesh gerektirir) sonuç sessizce "uyuştu" sayılmaz; `error` ile
    açıkça belirtilir.
    """
    from app.circuit.mesh import MeshAnalysisError, solve_mesh

    try:
        solution = solve_dc(netlist)
    except SolverError as exc:
        return MethodAgreement(False, error=f"düğüm analizi: {exc}")

    try:
        mesh_currents = solve_mesh(netlist)
    except MeshAnalysisError as exc:
        return MethodAgreement(False, error=f"çevre analizi: {exc}")

    # Karşılaştırma kaynak akımları üzerinden: düğüm analizi yalnızca onları
    # doğrudan veriyor. İşaret gösterimleri farklı olabildiği için mutlak
    # değer karşılaştırılıyor.
    disagreements = []
    nodal_currents = {}
    for name, current in solution.source_currents.items():
        nodal_currents[name] = current
        if name not in mesh_currents or abs(abs(current) - abs(mesh_currents[name])) > tolerance:
            disagreements.append(name)

    return MethodAgreement(
        agree=not disagreements,
        nodal=nodal_currents,
        mesh={k: v for k, v in mesh_currents.items() if k in nodal_currents},
        disagreements=tuple(disagreements),
    )


@dataclass
class CrossCheckResult:
    """İki bağımsız yöntemin aynı devrede aynı sonuca varıp varmadığı."""

    agree: bool
    reduction_value: float | None = None
    solver_value: float | None = None
    note: str = ""

    def describe(self) -> str:
        if self.reduction_value is None or self.solver_value is None:
            return f"Çapraz kontrol yapılamadı: {self.note}"
        verdict = "uyuşuyor" if self.agree else "UYUŞMUYOR"
        return (
            f"İki yöntem {verdict}: indirgeme {self.reduction_value:g} Ω, "
            f"çözücü {self.solver_value:g} Ω"
        )


def cross_check_resistance(
    netlist: Netlist, node_a: str, node_b: str, tolerance: float = 0.02
) -> CrossCheckResult:
    """Eşdeğer direnci İKİ BAĞIMSIZ yöntemle hesaplayıp karşılaştırır.

    Yöntem 1: `topology.py` — seri/paralel indirgeme (bu projenin kendi
              saf-Python kodu).
    Yöntem 2: `solve.py` — ngspice düğüm analizi (harici, olgun motor);
              devreye 1 V test kaynağı bağlanıp R = V/I ile bulunur.

    Neden değerli: kitabın cevabına İHTİYAÇ DUYMAZ. Çıkarılan 110
    alıştırmanın yarısında ayrıştırılabilir sayısal cevap yok; bu yöntem
    onlarda da topoloji okumasını sınayabilir. Ayrıca iki uygulama farklı
    olduğu için birinin hatası diğerinde ortaya çıkar.

    Sınırlama: köprü gibi seri/paralel ile indirgenemeyen devrelerde
    1. yöntem sonuç veremez — bu durumda "karşılaştırılamadı" döner,
    sessizce "uyuştu" sayılmaz.
    """
    from app.circuit.topology import equivalent_resistance

    resistors = [e for e in netlist.elements if e.kind == "resistor"]
    if not resistors:
        return CrossCheckResult(False, note="devrede direnç yok")

    reduction = equivalent_resistance(Netlist(resistors), node_a, node_b)

    # Test kaynağı: node_a ile node_b arasına 1 V bağlanır, çekilen akım
    # R = V/I ile eşdeğer direnci verir. Çözücü bir "gnd" düğümü istediği
    # için node_b geçici olarak "gnd" adına eşlenir.
    renamed = [
        Element(
            e.name,
            e.kind,
            (
                "gnd" if e.nodes[0] == node_b else e.nodes[0],
                "gnd" if e.nodes[1] == node_b else e.nodes[1],
            ),
            e.value,
        )
        for e in resistors
    ]
    probe = Element("probe", "voltage_source", (node_a, "gnd"), 1.0)

    try:
        solution = solve_dc(Netlist([*renamed, probe]))
        current = solution.source_currents["probe"]
        solver = abs(1.0 / current) if current else None
    except (SolverError, KeyError, ZeroDivisionError) as exc:
        return CrossCheckResult(False, reduction_value=reduction, note=f"çözücü: {exc}")

    if reduction is None:
        return CrossCheckResult(
            False,
            solver_value=solver,
            note="seri/paralel ile indirgenemedi (örn. köprü devresi)",
        )

    return CrossCheckResult(
        agree=verify_answer(reduction, solver, tolerance),
        reduction_value=reduction,
        solver_value=solver,
    )
