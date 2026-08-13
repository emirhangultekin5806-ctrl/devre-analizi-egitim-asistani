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

from app.circuit.netlist import Netlist
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
