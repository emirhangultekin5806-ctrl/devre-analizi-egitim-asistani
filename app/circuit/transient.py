"""Birinci dereceden geçici rejim (RC/RL) — Sadiku Bölüm 7.

Kitabın kendi tekniği birebir kodda (bkz. §7.5-7.6, "Eqs. 7.50-7.53"):
depolama elemanının (kapasitör/bobin) tepkisi

    x(t) = x(∞) + [x(0) − x(∞)]·e^(−t/τ)

biçimindedir; `x(0)` başlangıç değeri, `x(∞)` kalıcı (t→∞) değeri, `τ`
zaman sabitidir. Üç parça da MEVCUT çözücüler tekrar kullanılarak bulunur,
yeni bir yöntem icat edilmez:

- `x(0)`: anahtar/kaynak değişmeden ÖNCEKİ devre kalıcı durumdadır — bu
  `solve_dc` zaten kapasitörü açık devre, bobini kısa devre kabul ediyor,
  yani "before" netlist'i doğrudan çözmek x(0⁻)=x(0⁺) verir (depolama
  elemanının gerilimi/akımı ANİDEN değişemez — süreklilik ilkesi).
- `x(∞)`: "after" netlist'i de aynı DC varsayımıyla kalıcı duruma çözülür.
- `τ`: `theorems.thevenin_resistance` (bağımsız kaynakları öldür + 1 A test
  kaynağı enjekte et) depolama elemanı ÇIKARILMIŞ devrede yeniden
  kullanılır — bağımlı kaynak olsa da doğru sonuç verir, `topology.py`'nin
  seri/paralel indirgemesinden daha geneldir.

Devrenin "before"/"after" iki AYRI netlist olarak verilmesi bilinçli:
proje boyunca kurulan kural "önce netlist, sonra iddia" — bir anahtarın
t=0'da HANGİ YÖNE attığını görselden/context'ten tahmin etmek yerine,
çağıran taraf iki durumu da açıkça yazar (tıpkı kitabın kendisinin de
Fig. 7.43'ü "(a) t<0, (b) t≥0" diye iki ayrı devre çizmesi gibi).

Doğrulama (`tests/test_circuit_transient.py`): Sadiku Example 7.10 —
v(0)=15V, v(∞)=30V, τ=2s, v(1)=20.9V, v(4)=27.97V, kitapla birebir.
"""

import math
from dataclasses import dataclass

from app.circuit.netlist import Element, Netlist
from app.circuit.solve import ElementResult, SolverError, element_results, solve_dc
from app.circuit.theorems import thevenin_resistance


@dataclass(frozen=True)
class FirstOrderResponse:
    """x(t) = x(∞) + [x(0) − x(∞)]·e^(−t/τ), t ≥ 0 (Sadiku Eq. 7.53)."""

    kind: str  # "voltage" (kapasitör) | "current" (bobin)
    element_name: str
    x0: float
    x_inf: float
    tau: float

    def at(self, t: float) -> float:
        """x(t) — yalnızca t ≥ 0 için tanımlı (before/after geçişi t=0'da)."""
        if t < 0:
            raise ValueError("t negatif olamaz: bu yanıt yalnızca t≥0 (after devresi) için geçerli")
        return self.x_inf + (self.x0 - self.x_inf) * math.exp(-t / self.tau)

    def describe(self) -> str:
        symbol, unit = ("v", "V") if self.kind == "voltage" else ("i", "A")
        sign = "+" if self.x0 - self.x_inf >= 0 else "−"
        return (
            f"{symbol}(t) = {self.x_inf:.4g} {sign} {abs(self.x0 - self.x_inf):.4g}"
            f"·e^(−t/{self.tau:.4g}) {unit}  (t ≥ 0)"
        )


def _thevenin_resistance_without(netlist: Netlist, element_name: str, reference: str | None) -> float:
    """Verilen eleman ÇIKARILMIŞ devrede, onun eski iki ucundan görülen
    Thevenin direnci — zaman sabitinin R'si tam olarak budur."""
    target = netlist.by_name(element_name)
    remaining = Netlist([e for e in netlist.elements if e.name != element_name])
    node_a, node_b = target.nodes
    return thevenin_resistance(remaining, node_a, node_b, reference=reference)


def rc_step_response(
    before: Netlist, after: Netlist, capacitor_name: str, reference: str | None = None
) -> FirstOrderResponse:
    """Bir RC devresinin (anahtar/kaynak t=0'da değişen) geçiş yanıtı.

    `before`: t<0 devresi (kalıcı durumda olduğu varsayılır).
    `after`: t≥0 devresi.
    `capacitor_name`: iki netlist'te de AYNI adla bulunan kapasitör —
    fiziksel olarak aynı eleman, yalnızca çevresindeki devre değişmiştir.
    """
    cap_before = before.by_name(capacitor_name)
    cap_after = after.by_name(capacitor_name)
    if cap_before.kind != "capacitor" or cap_after.kind != "capacitor":
        raise SolverError(f"{capacitor_name}: kapasitör değil")
    if cap_before.value != cap_after.value:
        raise SolverError(f"{capacitor_name}: before/after arasında sığa değeri değişmemeli")

    v0 = solve_dc(before, reference=reference).voltage_across(*cap_before.nodes)
    v_inf = solve_dc(after, reference=reference).voltage_across(*cap_after.nodes)
    r_th = _thevenin_resistance_without(after, capacitor_name, reference)
    tau = r_th * cap_after.value
    return FirstOrderResponse("voltage", capacitor_name, v0, v_inf, tau)


def rl_step_response(
    before: Netlist, after: Netlist, inductor_name: str, reference: str | None = None
) -> FirstOrderResponse:
    """Bir RL devresinin geçiş yanıtı — `rc_step_response` ile simetrik.

    Bobin AKIMI süreklidir (gerilimi değil): i(0⁻)=i(0⁺). τ = L / R_th.
    """
    ind_before = before.by_name(inductor_name)
    ind_after = after.by_name(inductor_name)
    if ind_before.kind != "inductor" or ind_after.kind != "inductor":
        raise SolverError(f"{inductor_name}: bobin değil")
    if ind_before.value != ind_after.value:
        raise SolverError(f"{inductor_name}: before/after arasında endüktans değişmemeli")

    results_before = element_results(before, solve_dc(before, reference=reference))
    results_after_inf = element_results(after, solve_dc(after, reference=reference))
    i0 = results_before[inductor_name].current
    i_inf = results_after_inf[inductor_name].current
    r_th = _thevenin_resistance_without(after, inductor_name, reference)
    tau = ind_after.value / r_th
    return FirstOrderResponse("current", inductor_name, i0, i_inf, tau)


def snapshot_at(
    after: Netlist, response: FirstOrderResponse, t: float, reference: str | None = None
) -> dict[str, ElementResult]:
    """t anında TÜM elemanların akım/gerilim/gücü.

    Kitabın kendi tekniği: depolama elemanının o andaki değeri BİLİNDİĞİNDE
    (kapasitör → o değerde bir gerilim kaynağı, bobin → o değerde bir akım
    kaynağı), geri kalan devre sıradan bir DC devresi gibi çözülür —
    "the resistor current i can be discontinuous... it is always better to
    find v and then obtain i from v" (Example 7.11 metni).
    """
    target = after.by_name(response.element_name)
    value = response.at(t)
    if target.kind == "capacitor":
        replacement = Element(target.name, "voltage_source", target.nodes, value)
    elif target.kind == "inductor":
        replacement = Element(target.name, "current_source", target.nodes, value)
    else:
        raise SolverError(f"{response.element_name}: kapasitör ya da bobin değil")

    snapshot = Netlist(
        [replacement if e.name == target.name else e for e in after.elements]
    )
    return element_results(snapshot, solve_dc(snapshot, reference=reference))


# =============================================================================
# İkinci dereceden geçici rejim (RLC) — Sadiku Bölüm 8.
#
# Karakteristik denklem s² + 2αs + ω₀² = 0'ın kökleri α ile ω₀'ın
# karşılaştırılmasıyla üç durum verir (Sadiku §8.3 birebir):
#   α > ω₀ : AŞIRI SÖNÜMLÜ  — s1,2 = −α ± √(α²−ω₀²) (reel, farklı)
#   α = ω₀ : KRİTİK SÖNÜMLÜ — çift kök s = −α
#   α < ω₀ : AZ SÖNÜMLÜ     — s1,2 = −α ± jω_d, ω_d = √(ω₀²−α²)
#
# Seri RLC'de α = R/(2L); paralel RLC'de α = 1/(2RC) — devre "dual"i
# olduğu için tek fark budur, ω₀ = 1/√(LC) ikisinde de aynı.
#
# Doğrulama: Sadiku Example 8.3 (α=9, ω₀=10 → köklerin sınıflandırması) ve
# Example 8.4 (aynı devrenin tam yanıtı: i(t)=e^-9t(cos4.359t+0.6882sin4.359t) A,
# kitapla birebir).
# =============================================================================


@dataclass(frozen=True)
class SecondOrderResponse:
    """Kaynaksız (ya da t=0'da kaynağı ayrılan) 2. dereceden devrenin doğal tepkisi.

    `kind`: "current" (seri RLC → bobin akımı) | "voltage" (paralel RLC →
    kapasitör gerilimi) — hangi büyüklüğün x(t) olduğunu belirtir.
    """

    kind: str
    damping: str  # "overdamped" | "critically_damped" | "underdamped"
    alpha: float
    omega0: float
    s1: float | None = None
    s2: float | None = None
    omega_d: float | None = None
    a1: float = 0.0
    a2: float = 0.0

    def at(self, t: float) -> float:
        if t < 0:
            raise ValueError("t negatif olamaz")
        if self.damping == "overdamped":
            return self.a1 * math.exp(self.s1 * t) + self.a2 * math.exp(self.s2 * t)
        if self.damping == "critically_damped":
            return (self.a1 + self.a2 * t) * math.exp(-self.alpha * t)
        # underdamped
        return math.exp(-self.alpha * t) * (
            self.a1 * math.cos(self.omega_d * t) + self.a2 * math.sin(self.omega_d * t)
        )

    def describe(self) -> str:
        symbol = "i" if self.kind == "current" else "v"
        if self.damping == "overdamped":
            body = f"{self.a1:.4g}·e^({self.s1:.4g}t) + {self.a2:.4g}·e^({self.s2:.4g}t)"
        elif self.damping == "critically_damped":
            body = f"({self.a1:.4g} + {self.a2:.4g}t)·e^(−{self.alpha:.4g}t)"
        else:
            body = (
                f"e^(−{self.alpha:.4g}t)·[{self.a1:.4g}·cos({self.omega_d:.4g}t) "
                f"+ {self.a2:.4g}·sin({self.omega_d:.4g}t)]"
            )
        return f"{symbol}(t) = {body}  [{self.damping}]"


def _classify(kind: str, alpha: float, omega0: float, x0: float, dx0: float) -> SecondOrderResponse:
    """Sınıflandırma + başlangıç koşullarından (x(0), dx/dt(0)) A1/A2 katsayıları.

    Üç durumda da x(0)=x0 ve dx/dt(0)=dx0 iki denklemi A1,A2 için çözülür
    (Sadiku'nun Example 8.4'te elle yaptığı adımların aynısı).
    """
    if alpha > omega0:
        root = math.sqrt(alpha**2 - omega0**2)
        s1, s2 = -alpha + root, -alpha - root
        # x(t)=A1 e^(s1 t)+A2 e^(s2 t); x(0)=A1+A2=x0; dx/dt(0)=A1 s1+A2 s2=dx0
        a1 = (dx0 - s2 * x0) / (s1 - s2)
        a2 = x0 - a1
        return SecondOrderResponse(kind, "overdamped", alpha, omega0, s1=s1, s2=s2, a1=a1, a2=a2)
    if math.isclose(alpha, omega0, rel_tol=1e-9):
        # x(t)=(A1+A2 t) e^(−αt); x(0)=A1=x0; dx/dt(0)=A2−α A1=dx0
        a1 = x0
        a2 = dx0 + alpha * x0
        return SecondOrderResponse(kind, "critically_damped", alpha, omega0, a1=a1, a2=a2)
    omega_d = math.sqrt(omega0**2 - alpha**2)
    # x(t)=e^(−αt)(A1 cos ωd t+A2 sin ωd t); x(0)=A1=x0; dx/dt(0)=−α A1+ωd A2=dx0
    a1 = x0
    a2 = (dx0 + alpha * x0) / omega_d
    return SecondOrderResponse(kind, "underdamped", alpha, omega0, omega_d=omega_d, a1=a1, a2=a2)


def series_rlc_response(r: float, l: float, c: float, i0: float, di0: float) -> SecondOrderResponse:
    """Seri RLC'nin bobin akımı i(t) yanıtı — α = R/(2L), ω₀ = 1/√(LC).

    `i0` = i(0) (süreklilik ilkesi), `di0` = di/dt(0) = −[R·i(0)+v(0)]/L
    (Sadiku Eq. 8.4: KVL'den, L di/dt + Ri + v = 0).
    """
    alpha = r / (2 * l)
    omega0 = 1 / math.sqrt(l * c)
    return _classify("current", alpha, omega0, i0, di0)


def parallel_rlc_response(r: float, l: float, c: float, v0: float, dv0: float) -> SecondOrderResponse:
    """Paralel RLC'nin kapasitör gerilimi v(t) yanıtı — α = 1/(2RC), ω₀ = 1/√(LC).

    Seri RLC'nin "dual"idir (Sadiku §8.4): tek fark α formülü, ω₀ aynı.
    `v0` = v(0), `dv0` = dv/dt(0) = −[v(0)/R + i(0)]/C (KCL'den).
    """
    alpha = 1 / (2 * r * c)
    omega0 = 1 / math.sqrt(l * c)
    return _classify("voltage", alpha, omega0, v0, dv0)


def series_rlc_natural_response(
    before: Netlist,
    after: Netlist,
    inductor_name: str,
    capacitor_name: str,
    reference: str | None = None,
) -> SecondOrderResponse:
    """Gerçek bir netlist ÇİFTİNDEN seri RLC doğal tepkisini kurar.

    `i(0)`, `v(0)`: `before` devresinden süreklilik ilkesiyle (RC/RL
    fonksiyonlarındaki AYNI teknik).
    `di(0)/dt`: `after` devresinde L ve C, t=0⁺ değerlerine SABİTLENMİŞ
    birer kaynakla değiştirilip (`snapshot_at`'teki AYNI teknik) L'nin
    ÜZERİNDEKİ gerilim okunur: di/dt(0) = V_L(0⁺)/L.
    `R`: L ve C çıkarılmış devrede bağımsız kaynaklar öldürülüp ölçülen
    Thevenin direnci (`theorems` yeniden kullanılıyor) — devrede t≥0'da
    aktif bir kaynak kalmışsa (örn. adım girişi) bu artık "kaynaksız"
    olmayan bir yanıt verir; saf kaynaksız devre için `after`'da bağımsız
    kaynak bulunmamalıdır.
    """
    cap = before.by_name(capacitor_name)
    before_solution = solve_dc(before, reference=reference)
    i0 = element_results(before, before_solution)[inductor_name].current
    v0 = before_solution.voltage_across(*cap.nodes)

    l_value = after.by_name(inductor_name).value
    c_value = after.by_name(capacitor_name).value

    # di/dt(0) = V_L(0+)/L: L ve C'yi anlık değerlerine sabitleyip geri
    # kalan (artık salt dirençli) devreyi çözüyoruz.
    snapshot = Netlist(
        [
            Element(inductor_name, "current_source", after.by_name(inductor_name).nodes, i0)
            if e.name == inductor_name
            else (
                Element(capacitor_name, "voltage_source", after.by_name(capacitor_name).nodes, v0)
                if e.name == capacitor_name
                else e
            )
            for e in after.elements
        ]
    )
    v_l = element_results(snapshot, solve_dc(snapshot, reference=reference))[inductor_name].voltage
    di0 = v_l / l_value

    r_th = _series_loop_resistance(after, inductor_name, capacitor_name, reference)
    return series_rlc_response(r_th, l_value, c_value, i0, di0)


def _series_loop_resistance(
    netlist: Netlist, inductor_name: str, capacitor_name: str, reference: str | None
) -> float:
    """R-L-C tek çevriminde, L ve C'nin PAYLAŞTIĞI düğüm dışındaki iki
    "dış" uç arasında ölçülen Thevenin direnci — karakteristik denklemin R'si.

    L ve C'yi BÖLGE olarak (`solve_dc`'nin C'yi DC'de açık devre kabul
    etmesine güvenmeden) tamamen çıkarıp DIŞ uçlar arasında ölçmek zorunlu:
    L çıkarılıp C YERİNDE bırakılsaydı, C zaten DC'de açık devre kabul
    edildiği için o uç hiçbir dirençli yola bağlı kalmıyor (gerçek veride
    yakalandı — yanlış R_th, dolayısıyla yanlış sönüm sınıflandırması
    veriyordu). Bu fonksiyon yalnızca L ve C'nin BİRBİRİYLE KOMŞU olduğu
    (bir düğümü paylaştığı) basit seri döngüler için tanımlıdır — Sadiku
    Bölüm 8'in kapsadığı klasik durum.
    """
    inductor = netlist.by_name(inductor_name)
    capacitor = netlist.by_name(capacitor_name)
    shared = set(inductor.nodes) & set(capacitor.nodes)
    if len(shared) != 1:
        raise SolverError(
            f"{inductor_name} ve {capacitor_name} tek bir düğümü paylaşmıyor "
            "— bu fonksiyon yalnızca basit seri R-L-C çevrimlerini destekliyor"
        )
    shared_node = shared.pop()
    l_outer = inductor.other_node(shared_node)
    c_outer = capacitor.other_node(shared_node)
    remaining = Netlist(
        [e for e in netlist.elements if e.name not in (inductor_name, capacitor_name)]
    )
    return thevenin_resistance(remaining, l_outer, c_outer, reference=reference)
