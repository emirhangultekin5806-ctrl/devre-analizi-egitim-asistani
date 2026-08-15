"""Üç fazlı sistemler — Sadiku Bölüm 12.

Yeni bir çözüm yöntemi İCAT ETMİYOR: dengeli/dengesiz üç fazlı devreler,
üç fazı 120°'lik faz farklarıyla temsil eden SIRADAN bir AC netlist'idir
— `solve_ac`'in (bkz. `app/circuit/ac.py`) zaten çözdüğü türden. Bu modül
şunları ekler:

- Faz-hat gerilim/akım dönüşüm formülleri (Y ve Δ için, Sadiku §12.11
  Özet madde 4 ve Tablo 12.1).
- Dengeli yük için Y-Δ empedans dönüşümü: Z_Y = Z_Δ/3 — genel Δ-Y direnç
  dönüşümünün (`topology.delta_to_wye`) üç eşit kolun özel durumu.
- Güç formülleri, faz başına ve toplam (Eq. 12.46-12.53).
- `wye_source_wye_load`/`wye_source_delta_load`: kaynak+yükü GERÇEK bir AC
  netlist'ine çevirir (dengeli ya da dengesiz, nötr telli ya da telsiz) —
  `solve_ac` ile çözülür; kısayol değil TAM (KCL/KVL) çözüm. Dengesiz
  sistemler (Sadiku §12.8: "dengesiz sistemler doğrudan mesh/nodal analiz
  ile çözülür") bu yüzden EK KOD gerektirmiyor — `solve_ac` zaten geneldir.

**Empedans → R/L/C dönüşümü.** Kitabın çoğu üç fazlı örneği yükü doğrudan
karmaşık empedans olarak verir (ör. "ZY = 40 + j25 Ω"), R/L/C değeri ya da
frekans olarak değil — çünkü frekans önemsizdir, yalnızca empedans önemlidir.
`solve_ac` ise gerçek R/L/C değeri + frekansister. Kitabın KENDİ PSpice
çözümü de (Example 12.12) aynı sorunla karşılaşıyor ve ω=1 rad/s VARSAYIP
L=X, C=-1/X çeviriyor ("Since the operating frequency is not given... we
assume ω=1 rad/s"). Bu modül aynı tekniği kullanır (`DEFAULT_OMEGA`).
"""

import cmath
import math

from app.circuit.ac import ACSolution, solve_ac
from app.circuit.netlist import Element, Netlist

_SEQUENCE_SHIFT = {"abc": -120.0, "acb": 120.0}

# Kitabın kendi tekniği (Example 12.12): frekans önemsizse ω=1 rad/s
# varsayılır, yalnızca empedans doğru çıkacak şekilde L/C seçilir.
DEFAULT_OMEGA = 1.0


def _check_sequence(sequence: str) -> None:
    if sequence not in _SEQUENCE_SHIFT:
        raise ValueError(f"sequence 'abc' ya da 'acb' olmalı, verilen: {sequence!r}")


def balanced_phase_voltages(
    magnitude: float, sequence: str = "abc", reference_angle: float = 0.0
) -> tuple[complex, complex, complex]:
    """(Van, Vbn, Vcn) — dengeli faz gerilimleri (fazör, karmaşık sayı).

    "abc" (pozitif) sırasında Vbn, Van'dan 120° geride, Vcn 120° ileride
    (Vbn'e göre); "acb" (negatif) sırasında ters (bkz. Sadiku §12.11 Özet
    madde 1).
    """
    _check_sequence(sequence)
    shift = _SEQUENCE_SHIFT[sequence]
    van = cmath.rect(magnitude, math.radians(reference_angle))
    vbn = cmath.rect(magnitude, math.radians(reference_angle + shift))
    vcn = cmath.rect(magnitude, math.radians(reference_angle - shift))
    return van, vbn, vcn


def phase_to_line_voltage(v_phase: complex, sequence: str = "abc") -> complex:
    """V_p -> V_L (Y bağlantı): V_L = √3 V_p ∠30° ("abc" sırasında).

    Sadiku §12.11 Özet madde 4: Y-yükte V_L = √3 V_p, hat gerilimi faz
    gerilimini 30° öne alır ("abc" sırasında; "acb"'de 30° geriye).
    """
    _check_sequence(sequence)
    angle = 30.0 if sequence == "abc" else -30.0
    return v_phase * math.sqrt(3) * cmath.rect(1, math.radians(angle))


def line_to_phase_voltage(v_line: complex, sequence: str = "abc") -> complex:
    """V_L -> V_p (Y bağlantı): `phase_to_line_voltage`'ın tersi.

    Doğrulandı: Example 12.5 (Sadiku) — Vab=210∠0 (Δ kaynak) Y'e
    dönüştürülünce Van=121.2∠-30 V veriyor (kitapla birebir).
    """
    _check_sequence(sequence)
    angle = 30.0 if sequence == "abc" else -30.0
    return v_line / (math.sqrt(3) * cmath.rect(1, math.radians(angle)))


def delta_line_current(i_phase: complex, sequence: str = "abc") -> complex:
    """I_p -> I_L (Δ bağlantı): I_L = √3 I_p ∠-30° ("abc" sırasında)."""
    _check_sequence(sequence)
    angle = -30.0 if sequence == "abc" else 30.0
    return i_phase * math.sqrt(3) * cmath.rect(1, math.radians(angle))


def delta_phase_current(i_line: complex, sequence: str = "abc") -> complex:
    """`delta_line_current`'ın tersi."""
    _check_sequence(sequence)
    angle = -30.0 if sequence == "abc" else 30.0
    return i_line / (math.sqrt(3) * cmath.rect(1, math.radians(angle)))


def wye_impedance_from_delta(z_delta: complex) -> complex:
    """Dengeli yük: Z_Y = Z_Δ / 3 (Sadiku §12.6) — `topology.delta_to_wye`'ın
    üç kolu da EŞİT olduğu özel durumu (genel formül gerekmez)."""
    return z_delta / 3


def delta_impedance_from_wye(z_wye: complex) -> complex:
    """`wye_impedance_from_delta`'nın tersi: Z_Δ = 3 Z_Y."""
    return z_wye * 3


def phase_power(v_phase: complex, i_phase: complex) -> complex:
    """S_p = V_p · I_p* — faz başına karmaşık güç (Eq. 12.49)."""
    return v_phase * i_phase.conjugate()


def total_power(v_phase: complex, i_phase: complex) -> complex:
    """S = 3 S_p — toplam karmaşık güç, Y ve Δ yük için AYNI formül
    (Eq. 12.50-12.52; kitabın kendi notu: "Eq. (12.50) applies for both
    Y-connected and Δ-connected loads")."""
    return 3 * phase_power(v_phase, i_phase)


def total_power_from_line(v_line: float, i_line: float, angle_degrees: float) -> complex:
    """S = √3 V_L I_L ∠θ (Eq. 12.52) — yalnızca büyüklükler + yük açısı
    biliniyorsa doğrudan kısayol (Example 12.7/12.8 tarzı problemler,
    faz gerilimi/akımı hiç hesaplanmadan)."""
    magnitude = math.sqrt(3) * v_line * i_line
    return cmath.rect(magnitude, math.radians(angle_degrees))


def _series_impedance_elements(name: str, node_a: str, node_b: str, z: complex, omega: float) -> list[Element]:
    """Karmaşık bir empedansı R + (L ya da C) SERİ dizisine çevirir.

    Yalnızca gerçek kısım varsa tek direnç, yalnızca sanal kısım varsa tek
    L/C, ikisi de varsa aralarına yeni bir düğüm eklenip iki eleman
    döner (bkz. modül docstring'i, "Empedans → R/L/C dönüşümü").
    """
    resistance = z.real
    reactance = z.imag
    if reactance == 0:
        return [Element(f"{name}R", "resistor", (node_a, node_b), resistance)]
    if reactance > 0:
        reactive = Element(f"{name}L", "inductor", (node_a, node_b), reactance / omega)
    else:
        reactive = Element(f"{name}C", "capacitor", (node_a, node_b), -1 / (omega * reactance))
    if resistance == 0:
        return [reactive]
    mid = f"__{name}_mid"
    resistor = Element(f"{name}R", "resistor", (node_a, mid), resistance)
    reactive = Element(reactive.name, reactive.kind, (mid, node_b), reactive.value)
    return [resistor, reactive]


def _source_elements(name_prefix: str, va: complex, vb: complex, vc: complex, neutral: str) -> list[Element]:
    elements = []
    for label, phasor in (("a", va), ("b", vb), ("c", vc)):
        magnitude, angle = ACSolution.polar(phasor)
        elements.append(
            Element(f"{name_prefix}{label}", "voltage_source", (label, neutral), magnitude, phase=angle)
        )
    return elements


def wye_source_wye_load(
    van: complex,
    vbn: complex,
    vcn: complex,
    za: complex,
    zb: complex,
    zc: complex,
    neutral_wire: bool = True,
    omega: float = DEFAULT_OMEGA,
) -> Netlist:
    """Y-bağlı kaynak + Y-bağlı yük — dengeli ya da dengesiz.

    `neutral_wire=False`: kaynağın ve yükün nötr düğümleri AYRI kalır
    (3 telli sistem) — dengesiz bir yükte bu iki düğüm arasında gerçek bir
    gerilim farkı ("nötr kayması") oluşur, `solve_ac` bunu otomatik
    hesaplar (iki düğümü birbirine bağlamamak yeterli, ekstra kod gerekmez).

    Doğrulandı: Example 12.9 (Sadiku) — dengesiz Y yük (ZA=15, ZB=10+j5,
    ZC=6-j8Ω), nötr telli, hat akımları ve nötr akımı kitapla birebir.

    Kaynağın nötr düğümü her zaman "gnd" adını alır (`solve_ac`'in
    referans düğüm olarak aradığı ad, bkz. `app/circuit/solve.py`) — bu
    aynı zamanda kitabın da faz gerilimlerini ("Van" vb.) ölçtüğü doğal
    referans noktasıdır.
    """
    elements = _source_elements("V", van, vbn, vcn, "gnd")
    # küçük harf: ngspice düğüm adlarını küçük harfe çeviriyor, büyük
    # harfli bir ad `solve_ac`'in sonuç sözlüğünde aranınca (case-sensitive)
    # bulunamıyordu -- ölçüldü, `voltage_across("N", ...)` KeyError verdi.
    load_neutral = "gnd" if neutral_wire else "n_load"
    elements += _series_impedance_elements("Za", "a", load_neutral, za, omega)
    elements += _series_impedance_elements("Zb", "b", load_neutral, zb, omega)
    elements += _series_impedance_elements("Zc", "c", load_neutral, zc, omega)
    return Netlist(elements)


def wye_source_delta_load(
    van: complex,
    vbn: complex,
    vcn: complex,
    zab: complex,
    zbc: complex,
    zca: complex,
    omega: float = DEFAULT_OMEGA,
) -> Netlist:
    """Y-bağlı kaynak + Δ-bağlı yük — dengeli ya da dengesiz.

    Δ-bağlı KAYNAK modellenmiyor (kitabın kendi uyarısı: "a delta-connected
    source is a loop of voltage sources — which PSpice does not like",
    §12.9) — Δ kaynaklı bir devre önce Y'e dönüştürülüp (bkz.
    `line_to_phase_voltage`) bu fonksiyona verilmeli (Example 12.5'te
    olduğu gibi).
    """
    elements = _source_elements("V", van, vbn, vcn, "gnd")
    elements += _series_impedance_elements("Zab", "a", "b", zab, omega)
    elements += _series_impedance_elements("Zbc", "b", "c", zbc, omega)
    elements += _series_impedance_elements("Zca", "c", "a", zca, omega)
    return Netlist(elements)


def solve(netlist: Netlist, omega: float = DEFAULT_OMEGA) -> ACSolution:
    """`wye_source_wye_load`/`wye_source_delta_load` ile kurulan bir
    netlist'i çözer. `omega`, netlist kurulurken kullanılanla AYNI olmalı
    (empedanslar o açısal frekansa göre R/L/C'ye çevrildi — bkz. modül
    docstring'i)."""
    return solve_ac(netlist, frequency=omega / (2 * math.pi))


def line_current(solution: ACSolution, source_name: str) -> complex:
    """`source_name` kaynağının hat akımı (kaynaktan yüke akan yön,
    örn. "Va" -> a hattındaki akım)."""
    return solution.source_currents[source_name]


def neutral_current(ia: complex, ib: complex, ic: complex) -> complex:
    """I_n = -(Ia + Ib + Ic) — dengesiz Y yükte nötr hattı akımı (Eq. 12.60).
    Dengeli bir sistemde bu her zaman sıfırdır."""
    return -(ia + ib + ic)
