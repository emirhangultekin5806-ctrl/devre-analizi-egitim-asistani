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
import math
from dataclasses import dataclass, field

from app.circuit.netlist import Netlist
from app.circuit.solve import _BRANCH_PREFIX, GROUND_NODES, SolverError, _ground_of

# solve.py'deki ElementResult/element_results/power_balance'ın fazör
# karşılığı -- DC yolu bunlarsız zaten çalışıyordu ama AC yolunun eleman
# bazlı sonuç/tutarlılık kontrolü hiç yoktu (solve_ac yalnızca düğüm
# gerilimlerini veriyordu). solve_from_extraction.py'nin DC/AC'yi aynı
# anda deneyip iki yoldan da eleman sonucu + Tellegen kontrolü üretebilmesi
# için eklendi.


@dataclass
class ACSolution:
    """Belirli bir frekanstaki fazör çözümü."""

    frequency: float
    node_voltages: dict[str, complex] = field(default_factory=dict)
    source_currents: dict[str, complex] = field(default_factory=dict)
    # bkz. solve.py Solution.reference -- toprak sembolü olmayan şekillerde
    # çağıranın seçtiği düğüm; çözümde 0V'tur, ngspice çıktısında yer almaz
    # (ground olarak SPICE'a verildiği için node_voltages'ta hiç anahtarı
    # olmaz -- reference alanı olmadan bu düğüm sorgulanınca KeyError verirdi,
    # bkz. `solve_ac`'in `reference` parametresi).
    reference: str | None = None

    def voltage_across(self, node_a: str, node_b: str) -> complex:
        return self._v(node_a) - self._v(node_b)

    def _v(self, node: str) -> complex:
        # ngspice düğüm adlarını küçük harfe çeviriyor (SPICE büyük/küçük
        # harf duyarsızdır); `node_voltages` bu yüzden hep küçük harfle
        # anahtarlanır (bkz. `solve_ac`) — sorgu da aynı şekilde küçük
        # harfe çevrilir, aksi halde büyük harfli bir düğüm adı ("N" gibi)
        # burada sessizce KeyError verirdi (gerçek veride yakalandı:
        # `threephase.py`, bkz. modül geçmişi).
        key = node.lower()
        if key in GROUND_NODES or (self.reference is not None and key == self.reference.lower()):
            return 0j
        if key not in self.node_voltages:
            raise KeyError(f"{node!r} düğümü çözümde yok")
        return self.node_voltages[key]

    @staticmethod
    def polar(value: complex) -> tuple[float, float]:
        """Karmaşık fazörü (genlik, derece cinsinden faz) olarak verir."""
        return abs(value), cmath.phase(value) * 180 / cmath.pi

    def describe_node(self, node: str) -> str:
        magnitude, angle = self.polar(self._v(node))
        return f"V({node}) = {magnitude:.4g} ∠ {angle:.2f}°"


def impedance(kind: str, value: float, frequency: float, phase_degrees: float = 0.0) -> complex:
    """Elemanın belirli frekanstaki empedansı (Ω).

    R -> R,  L -> jωL,  C -> 1/(jωC) = -j/(ωC),
    impedance -> value∠phase_degrees (sabit, frekanstan BAĞIMSIZ -- Sadiku'nun
    "Z = 8+j6 Ω" kutusu zaten kendi empedansını doğrudan verir, R/L/C gibi
    frekanstan türetilmez). `phase_degrees` yalnızca bu türde anlamlıdır
    (bkz. netlist.py ELEMENT_KINDS yorumu -- diğer türlerde yok sayılır).
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
    if kind == "impedance":
        return cmath.rect(value, math.radians(phase_degrees))
    raise SolverError(f"{kind}: empedansı tanımlı değil")


def _add_fixed_impedance(circuit, node_fn, name: str, a: str, b: str, z: complex, omega: float) -> None:
    """Sabit bir karmaşık empedansı (Z = r + jx) ngspice'a enjekte eder.

    ngspice'ta "sabit karmaşık empedans" diye bir eleman YOK -- ama solve_ac
    zaten HER ZAMAN tek bir frekansta çözüyor, bu yüzden Z'yi bu TEK
    frekansta AYNI empedansı üretecek bir R + (L ya da C) seri kombinasyonu
    olarak taklit edebiliriz (başka bir frekansta bu R/L/C yanlış Z verirdi,
    ama solve_ac hiçbir zaman ikinci bir frekansta bu değerleri kullanmaz).
    r=0 ise R elemanı tamamen atlanır (gereksiz sıfır-dirençli eleman
    eklememek için), x=0 ise (saf dirençli kutu) tek bir R yeterlidir.
    """
    r, x = z.real, z.imag
    # cmath.rect'ten gelen r/x, "tam 0 olmasi gereken" acilarda (90, 180
    # derece gibi) kayan-nokta yuvarlamasi yuzunden TAM 0.0 CIKMAZ (orn.
    # cos(90 derece) ~ 6e-17) -- BULUNDU (gercek cagriyla, 2026-08-24):
    # bu, neredeyse-tekil (~1e-16 Ω) bir direnc elemanina yol aciyordu,
    # ngspice'in matris cozumu bozulup TAMAMEN yanlis bir sonuc uretiyordu
    # (guc dengesi ~0 yerine -80W gibi). Buyuklige oranli bir toleransla
    # GERCEKTEN sifir sayilip TAM 0.0'a yuvarlaniyor.
    tol = abs(z) * 1e-9
    if abs(r) < tol:
        r = 0.0
    if abs(x) < tol:
        x = 0.0
    na, nb = node_fn(a), node_fn(b)
    if x == 0:
        circuit.R(name, na, nb, r)
        return
    mid = na if r == 0 else f"__z_{name}"
    if r != 0:
        circuit.R(f"{name}_r", na, mid, r)
    if x > 0:
        circuit.L(f"{name}_x", mid, nb, x / omega)
    else:
        circuit.C(f"{name}_x", mid, nb, -1 / (omega * x))


# Akimi bir bagimli kaynak tarafindan OKUNABILEN eleman turleri. Pasif
# olanlarda araya 0 V'luk "hayalet ampermetre" konur (SPICE'ta CCVS yalnizca
# bir GERILIM KAYNAGININ dal akimini referans alabilir); gerilim kaynaginin
# dal akimini ise SPICE zaten dogrudan sunar, hile gerekmez.
_PASSIVE_KINDS = ("resistor", "capacitor", "inductor", "impedance")
_SENSEABLE_KINDS = (*_PASSIVE_KINDS, "voltage_source")


def _ccvs_reference(kind: str, control_name: str) -> str:
    """CCVS'in referans alacagi SPICE gerilim-kaynagi adi.

    Pasif elemanda hayalet ampermetre ("Vamm_<ad>"), gerilim kaynaginda
    elemanin KENDI SPICE adi ("V<ad>") -- ikisi de kucuk harfe cevrilir
    (SPICE buyuk/kucuk harf duyarsiz, PySpice referansi boyle bekliyor).
    """
    return f"v{control_name}" if kind == "voltage_source" else f"vamm_{control_name}"


def _add_phased_source(circuit, prefix: str, name: str, plus, minus, magnitude: float, phase: float) -> None:
    """Faz açılı bağımsız kaynak — ham SPICE satırıyla (bkz. `solve_ac` notu).

    Yalnızca `.ac()` analizi çalıştırılacağı için DC/geçici bileşen
    önemsiz; `DC 0` ile sıfırlanıyor, yalnızca AC genlik+faz kullanılıyor.
    """
    circuit.raw_spice += f"{prefix}{name} {plus} {minus} DC 0 AC {magnitude} {phase}\n"


def solve_ac(netlist: Netlist, frequency: float, reference: str | None = None) -> ACSolution:
    """Devreyi verilen frekansta fazör olarak çözer.

    Kaynaklar bu analizde birim genlikli AC kaynağı olarak sürülür; genlik
    `Element.value` ile, faz `Element.phase` (derece) ile ölçeklenir —
    varsayılan 0°.

    `reference`: şekilde toprak sembolü çizilmemişse referans alınacak
    düğüm -- solve_dc'deki aynı parametre/mantık (bkz. `_ground_of`).
    OLCULDU (Sadiku Figure 9.40/9.81): kitabın birçok AC şekli toprak
    sembolü ÇİZMİYOR, bu parametre olmadan solve_ac hep "referans yok"
    hatasıyla durup AC yolu hiç denenemiyordu.
    """
    from PySpice.Spice.Netlist import Circuit

    ground = _ground_of(netlist, reference)

    circuit = Circuit("ac")
    omega = 2 * cmath.pi * frequency

    def node(name: str):
        return circuit.gnd if name == ground else name

    # Akim-kontrollu bagimli kaynaklarin OKUDUGU elemanlar. SPICE'ta CCVS
    # yalnizca bir GERILIM KAYNAGININ dal akimini referans alabilir, bu
    # yuzden pasif bir elemanin akimi ancak araya 0 V'luk "hayalet
    # ampermetre" konarak okunur (bkz. solve.py'deki ayni desen -- DC
    # tarafinda zaten vardi, AC tarafinda bagimli kaynaklar HIC
    # desteklenmiyordu: vcvs/ccvs asagidaki else'e dusup "AC cozumde
    # desteklenmiyor" hatasi veriyordu).
    sensed = {e.control_element for e in netlist.elements if e.control_element is not None}
    by_name = {e.name: e for e in netlist.elements}
    # Pasif elemanin akimi hayalet ampermetreyle okunur; GERILIM KAYNAGININ
    # dal akimini ise SPICE zaten dogrudan veriyor (hile GEREKMEZ). Akim
    # kaynagi disarida: akimi zaten kendi degeri, ama CCVS referansi icin
    # bir gerilim kaynagi dali gerekiyor -- kapsam disi, acikca reddediliyor.
    unsupported = sorted(
        n for n in sensed if n not in by_name or by_name[n].kind not in _SENSEABLE_KINDS
    )
    if unsupported:
        raise SolverError(
            "Kontrol akımı yalnızca pasif eleman (direnç/bobin/kondansatör/empedans) ya da "
            f"gerilim kaynağı üzerinden ölçülebiliyor; eşleşmeyen: {unsupported}"
        )

    has_source = False
    for element in netlist.elements:
        a, b = element.nodes
        if element.value is None:
            raise SolverError(f"{element.name}: değer verilmemiş")
        # bkz. solve.py'deki ayni kontrol -- 0 Ω direnc empedans hesabinda
        # (element_results_ac -> impedance) sifira bolmeye yol acar.
        if element.kind == "resistor" and element.value == 0:
            raise SolverError(f"{element.name}: direnç değeri 0 -- muhtemelen okuma hatası, çözülemez")
        # AYNI risk kapasitorde de var (BULUNDU, 2026-08-21 denetimi, gercek
        # cagriyla dogrulandi): solve_ac 0F'lik bir kapasitoru SESSIZCE kabul
        # ediyor (ngspice hata vermiyor), ama element_results_ac->impedance()
        # 1/(jωC) hesabinda C=0 ile ZeroDivisionError firlatiyor -- cozum
        # BASARILI gorunup sonuc adiminda cokuyordu. Bobin (jωL) bu riski
        # TASIMAZ (carpim, bolme degil) ama 0H de fiziksel olarak ayni sekilde
        # anlamsiz (okuma hatasi) -- tutarlilik icin o da erken reddediliyor.
        if element.kind in ("capacitor", "inductor") and element.value == 0:
            raise SolverError(f"{element.name}: {element.kind} değeri 0 -- muhtemelen okuma hatası, çözülemez")
        # AYNI risk empedans kutusunda da var -- element_results_ac'teki
        # V/Z bölümü Z=0 ile çöker (bkz. yukarıdaki resistor/capacitor/
        # inductor kontrolleriyle AYNI mantık).
        if element.kind == "impedance" and element.value == 0:
            raise SolverError(f"{element.name}: impedance değeri 0 -- muhtemelen okuma hatası, çözülemez")
        # Akim-kontrollu bir bagimli kaynagin OKUDUGU pasif eleman: ikinci
        # ucu hayali bir ara dugume kaydirilir ve arasina 0 V'luk kaynak
        # ("hayalet ampermetre") konur -- o kaynagin dal akimi elemanin
        # GERCEK akimidir. Sonuclar etkilenmez: 0 V'luk kaynak ideal, hayali
        # dugumun gerilimi asil ucla her zaman aynidir.
        sensed_here = element.name in sensed and element.kind in _PASSIVE_KINDS
        b_eff = f"__amm_{element.name}" if sensed_here else b

        if element.kind == "resistor":
            circuit.R(element.name, node(a), node(b_eff), element.value)
        elif element.kind == "capacitor":
            circuit.C(element.name, node(a), node(b_eff), element.value)
        elif element.kind == "inductor":
            circuit.L(element.name, node(a), node(b_eff), element.value)
        elif element.kind == "impedance":
            z = cmath.rect(element.value, math.radians(element.phase))
            _add_fixed_impedance(circuit, node, element.name, a, b_eff, z, omega)
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
        elif element.kind == "vcvs":
            nc_plus, nc_minus = element.control_nodes
            circuit.VCVS(element.name, node(a), node(b), node(nc_plus), node(nc_minus), element.value)
            has_source = True
        elif element.kind == "ccvs":
            reference = _ccvs_reference(by_name[element.control_element].kind, element.control_element)
            circuit.CCVS(element.name, node(a), node(b), reference, element.value)
            has_source = True
        else:
            raise SolverError(f"{element.name}: {element.kind} AC çözümde desteklenmiyor")

        if sensed_here:
            circuit.V(f"amm_{element.name}", node(b_eff), node(b), 0)

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
    # Küçük harf: ngspice düğüm adlarını (SPICE büyük/küçük harf duyarsız
    # olduğu için) sessizce küçük harfe çeviriyor — burada da AÇIKÇA küçük
    # harfe çevrilip anahtarlanır, `ACSolution._v()`'nin sorgu tarafında
    # yaptığı küçültmeyle SİMETRİK olsun diye (aksi halde ngspice'ın kendi
    # davranışına dolaylı olarak güvenilmiş olurdu).
    voltages = {
        str(name).lower(): complex(waveform.as_ndarray()[0])
        for name, waveform in analysis.nodes.items()
    }
    raw = {
        str(name).lower(): -complex(waveform.as_ndarray()[0])
        for name, waveform in analysis.branches.items()
    }
    # Dal akimi adlandirmasi DC ile AYNI (SPICE onek + eleman adi): gerilim
    # kaynagi "v...", VCVS "e...", CCVS "h..." -- solve.py'deki _BRANCH_PREFIX
    # tek dogru kaynak, burada tekrar tanimlanmiyor ki ikisi birbirinden
    # sessizce sapmasin.
    currents = {
        element.name: raw[f"{_BRANCH_PREFIX[element.kind]}{element.name}".lower()]
        for element in netlist.elements
        if element.kind in _BRANCH_PREFIX
        and f"{_BRANCH_PREFIX[element.kind]}{element.name}".lower() in raw
    }
    return ACSolution(frequency=frequency, node_voltages=voltages, source_currents=currents, reference=ground)


@dataclass(frozen=True)
class ACElementResult:
    """Tek bir eleman için fazör akım/gerilim/güç -- solve.py'deki
    ElementResult'ın karmaşık karşılığı, aynı pasif işaret kuralıyla."""

    name: str
    kind: str
    current: complex
    voltage: complex
    power: complex

    def describe(self) -> str:
        i_mag, i_ang = ACSolution.polar(self.current)
        v_mag, v_ang = ACSolution.polar(self.voltage)
        p_mag, p_ang = ACSolution.polar(self.power)
        return (
            f"{self.name}: I = {i_mag:.4g}∠{i_ang:.1f}° A, "
            f"V = {v_mag:.4g}∠{v_ang:.1f}° V, |S| = {p_mag:.4g} VA∠{p_ang:.1f}°"
        )


def element_results_ac(netlist: Netlist, solution: ACSolution, frequency: float) -> dict[str, ACElementResult]:
    """Her eleman için fazör akım/gerilim/güç -- solve.py'deki element_results'ın AC karşılığı."""
    results: dict[str, ACElementResult] = {}
    for element in netlist.elements:
        a, b = element.nodes
        voltage = solution.voltage_across(a, b)

        if element.kind in ("resistor", "capacitor", "inductor", "impedance"):
            current = voltage / impedance(element.kind, element.value, frequency, element.phase)
        elif element.kind == "current_source":
            current = cmath.rect(element.value, cmath.pi / 180 * element.phase)
        elif element.kind in ("voltage_source", "vcvs", "ccvs"):
            # solve_ac kaynaktan ÇIKAN akımı pozitif veriyor (bkz. DC
            # tarafındaki aynı işaret notu) -- pasif işaret kuralına
            # çevirmek için ters çevrilir. vcvs/ccvs de aynı kurala tabi
            # (solve.py'deki element_results ile BİREBİR aynı davranış --
            # orada zaten üçü tek dalda toplanmıştı, AC tarafında bağımlı
            # kaynaklar hiç desteklenmediği için eksik kalmıştı).
            current = -solution.source_currents.get(element.name, 0j)
        else:
            raise SolverError(f"{element.name}: {element.kind} AC çözümde desteklenmiyor")

        results[element.name] = ACElementResult(
            name=element.name,
            kind=element.kind,
            current=current,
            voltage=voltage,
            power=voltage * current.conjugate(),
        )
    return results


def power_balance_ac(results: dict[str, ACElementResult]) -> complex:
    """Karmaşık Tellegen kontrolü: sum(V·conj(I)) ~ 0 olmalı (bkz. solve.py power_balance)."""
    return sum(result.power for result in results.values())
