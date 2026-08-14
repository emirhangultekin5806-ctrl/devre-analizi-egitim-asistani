"""AC (fazör) analizi — Devre Analizi 2'nin çekirdeği.

`solve.py` yalnızca DC çalışma noktasını çözüyordu: kapasitör açık devre,
bobin kısa devre. Bu, projenin kapsamının yarısını (Devre Analizi 2 —
fazörler, empedans, frekans tepkisi) dışarıda bırakıyordu. Bu modül o
boşluğu kapatır.

Sonuçlar KARMAŞIK sayıdır (fazör): genlik + faz. Ders kitabı gösterimi
`10∠-45° V` biçimindedir; `polar()` bunu üretir.

Önemli ayrıntı: PySpice'ın `WaveForm` sarmalayıcısı karmaşık değeri float'a
çevirip sanal kısmı ATIYOR (`ComplexWarning`). Gerçek veride yakalandı:
RC devresinde beklenen 0.707∠-45° yerine 0.5∠0° görünüyordu. Bu yüzden
değerler `as_ndarray()` ile ham numpy dizisinden okunuyor.
"""

import cmath
from dataclasses import dataclass, field

from app.circuit.netlist import Netlist
from app.circuit.solve import GROUND_NODES, SolverError


@dataclass
class ACSolution:
    """Belirli bir frekanstaki fazör çözümü."""

    frequency: float
    node_voltages: dict[str, complex] = field(default_factory=dict)
    source_currents: dict[str, complex] = field(default_factory=dict)

    def voltage_across(self, node_a: str, node_b: str) -> complex:
        return self._v(node_a) - self._v(node_b)

    def _v(self, node: str) -> complex:
        if node.lower() in GROUND_NODES:
            return 0j
        if node not in self.node_voltages:
            raise KeyError(f"{node!r} düğümü çözümde yok")
        return self.node_voltages[node]

    @staticmethod
    def polar(value: complex) -> tuple[float, float]:
        """Karmaşık fazörü (genlik, derece cinsinden faz) olarak verir."""
        return abs(value), cmath.phase(value) * 180 / cmath.pi

    def describe_node(self, node: str) -> str:
        magnitude, angle = self.polar(self._v(node))
        return f"V({node}) = {magnitude:.4g} ∠ {angle:.2f}°"


def impedance(kind: str, value: float, frequency: float) -> complex:
    """Elemanın belirli frekanstaki empedansı (Ω).

    R -> R,  L -> jωL,  C -> 1/(jωC) = -j/(ωC)
    """
    omega = 2 * cmath.pi * frequency
    if kind == "resistor":
        return complex(value, 0)
    if kind == "inductor":
        return 1j * omega * value
    if kind == "capacitor":
        if omega == 0:
            return complex("inf")  # DC'de açık devre
        return 1 / (1j * omega * value)
    raise SolverError(f"{kind}: empedansı tanımlı değil")


def _add_phased_source(circuit, prefix: str, name: str, plus, minus, magnitude: float, phase: float) -> None:
    """Faz açılı bağımsız kaynak — ham SPICE satırıyla (bkz. `solve_ac` notu).

    Yalnızca `.ac()` analizi çalıştırılacağı için DC/geçici bileşen
    önemsiz; `DC 0` ile sıfırlanıyor, yalnızca AC genlik+faz kullanılıyor.
    """
    circuit.raw_spice += f"{prefix}{name} {plus} {minus} DC 0 AC {magnitude} {phase}\n"


def solve_ac(netlist: Netlist, frequency: float) -> ACSolution:
    """Devreyi verilen frekansta fazör olarak çözer.

    Kaynaklar bu analizde birim genlikli AC kaynağı olarak sürülür; genlik
    `Element.value` ile, faz `Element.phase` (derece) ile ölçeklenir —
    varsayılan 0°.
    """
    from PySpice.Spice.Netlist import Circuit

    ground = None
    for node in netlist.nodes():
        if node.lower() in GROUND_NODES:
            ground = node
            break
    if ground is None:
        raise SolverError(
            f"Devrede referans (toprak) düğümü yok. Beklenen: {sorted(GROUND_NODES)}"
        )

    circuit = Circuit("ac")

    def node(name: str):
        return circuit.gnd if name == ground else name

    has_source = False
    for element in netlist.elements:
        a, b = element.nodes
        if element.value is None:
            raise SolverError(f"{element.name}: değer verilmemiş")
        if element.kind == "resistor":
            circuit.R(element.name, node(a), node(b), element.value)
        elif element.kind == "capacitor":
            circuit.C(element.name, node(a), node(b), element.value)
        elif element.kind == "inductor":
            circuit.L(element.name, node(a), node(b), element.value)
        # ac_magnitude ZORUNLU: `amplitude` yalnızca zaman-domeni (SIN)
        # genliğini ayarlıyor, AC analizinde kullanılan büyüklük bu değil.
        # Yalnızca `amplitude` verildiğinde ngspice AC genliğini 1 V kabul
        # ediyordu: 10 V'luk seri RLC rezonansında akım 0.2 A yerine 0.02 A
        # çıkıyordu (gerçek veride yakalandı — genliği 1 olan bir devreyle
        # test edilseydi bu hata görünmezdi).
        elif element.kind == "voltage_source":
            if element.phase:
                # PySpice'ın SinusoidalVoltageSource sarmalayıcısı AC faz
                # parametresini desteklemiyor (yalnızca DC/AC genlik) — ham
                # SPICE satırı gerekiyor: "DC 0 AC genlik faz". Elle kurulan
                # bir devrede doğrulandı: 10∠30° verilince ngspice tam
                # olarak 10∠30° döndürüyor.
                _add_phased_source(circuit, "V", element.name, node(a), node(b), element.value, element.phase)
            else:
                circuit.SinusoidalVoltageSource(
                    element.name,
                    node(a),
                    node(b),
                    amplitude=element.value,
                    frequency=frequency,
                    ac_magnitude=element.value,
                )
            has_source = True
        elif element.kind == "current_source":
            if element.phase:
                _add_phased_source(circuit, "I", element.name, node(a), node(b), element.value, element.phase)
            else:
                circuit.SinusoidalCurrentSource(
                    element.name,
                    node(a),
                    node(b),
                    amplitude=element.value,
                    frequency=frequency,
                    ac_magnitude=element.value,
                )
            has_source = True
        else:
            raise SolverError(f"{element.name}: {element.kind} AC çözümde desteklenmiyor")

    if not has_source:
        raise SolverError("Devrede kaynak yok")

    try:
        analysis = circuit.simulator().ac(
            start_frequency=frequency,
            stop_frequency=frequency,
            number_of_points=1,
            variation="lin",
        )
    except Exception as exc:
        raise SolverError(f"ngspice AC çözemedi: {exc}") from exc

    # as_ndarray(): PySpice'ın sarmalayıcısı sanal kısmı atıyor (bkz. modül
    # docstring'i) — ham diziden okunmalı.
    voltages = {
        str(name): complex(waveform.as_ndarray()[0]) for name, waveform in analysis.nodes.items()
    }
    raw = {
        str(name).lower(): -complex(waveform.as_ndarray()[0])
        for name, waveform in analysis.branches.items()
    }
    currents = {
        element.name: raw[f"v{element.name}".lower()]
        for element in netlist.elements
        if element.kind == "voltage_source" and f"v{element.name}".lower() in raw
    }
    return ACSolution(frequency=frequency, node_voltages=voltages, source_currents=currents)
