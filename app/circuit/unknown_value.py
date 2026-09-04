"""Bir direncin KENDİ değeri bilinmiyorsa ama üzerindeki dal gerilimi
biliniyorsa (bkz. Test Soruları/Soru15: "Find R", şekilde R'nin değeri hiç
yazmıyor, onun yerine üzerinde "+10V-" çizili), R'yi Kirchhoff akım/gerilim
yasalarıyla (KCL/KVL) doğrudan bulur.

Kullanıcının AÇIKÇA reddettiği yol: bilinmeyen direncin yerine bir kaynak
KOYMAK (netlist'i/topolojiyi bozar). Burada öyle bir şey YOK -- bu modül
`app/circuit/netlist.py`/`solve.py`'ye hiç dokunmaz, ngspice/PySpice'a hiç
gitmez. Devrenin geri kalanı için standart düğüm gerilimi (nodal) denklemleri
KENDİ kuruluyor; bilinmeyen dalın gerilimi (bir "kaynak" değil, sadece
BİLİNEN bir sınır koşulu) bu denklemlere aynen bir düğüm gerilimi farkı gibi
girer -- tıpkı kullanıcının elle yaptığı gibi (KVL: 50V - 10V = 40V, 40V/10Ω
= 4A, 10V/4A = 2.5Ω).

Kutuplama (dal geriliminin hangi yönde olduğu) OCR'dan gelmiyor -- OCR
"+10V-" işaretini kaybedip yalnız büyüklüğü ("10 V") bırakıyor (bkz.
devre-yolo-dedektor/label_assign.py branch_voltage_hints). Bu yüzden iki
yön de denenir; DİRENÇ ASLA NEGATİF OLAMAZ fiziksel kısıtı doğru yönü
belirler -- tahmin değil eleme (bu projenin her yerindeki aynı felsefe,
bkz. label_assign.py modül docstring'i).
"""
from __future__ import annotations

import numpy as np

from app.circuit.netlist import Netlist
from app.circuit.solve import SolverError, GROUND_NODES

# Bu ilk sürüm yalnızca DC + direnç + bağımsız gerilim kaynağı destekler --
# Soru15'te ihtiyaç bu. Kapasitör/bobin/bağımlı kaynak/akım kaynağı GÖRÜLMEDEN
# eklenmiyor (YAGNI, bkz. proje hafızası).
_SUPPORTED_KINDS = {"resistor", "voltage_source"}


def _ground_of(netlist: Netlist, reference: str | None) -> str:
    if reference is not None:
        return reference
    for node in netlist.nodes():
        if node.lower() in GROUND_NODES:
            return node
    raise SolverError("Referans düğüm yok ve `reference=` verilmedi")


def solve_unknown_resistor(
    netlist: Netlist, unknown_name: str, branch_voltage_magnitude: float, reference: str | None = None
) -> float:
    """`unknown_name` adlı direncin (value=None) kendi direncini bulur.

    `branch_voltage_magnitude`: o direncin İKİ UCU ARASINDAKİ gerilimin
    BÜYÜKLÜĞÜ (yönü bilinmiyor, bkz. modül docstring'i) -- her zaman pozitif.
    """
    unknown = netlist.by_name(unknown_name)
    if unknown.kind != "resistor" or unknown.value is not None:
        raise SolverError(f"{unknown_name}: değeri bilinmeyen bir direnç olmalı")
    if branch_voltage_magnitude <= 0:
        raise SolverError("dal gerilimi büyüklüğü pozitif olmalı")

    unsupported = sorted(
        {e.kind for e in netlist.elements}
        - _SUPPORTED_KINDS
    )
    if unsupported:
        raise SolverError(
            f"bilinmeyen direnç çözümü şu türleri desteklemiyor: {unsupported} "
            "(yalnızca direnç + bağımsız gerilim kaynağı, DC)"
        )
    other_unknown = [
        e.name for e in netlist.elements
        if e.name != unknown_name and e.kind == "resistor" and e.value is None
    ]
    if other_unknown:
        raise SolverError(f"birden fazla değeri bilinmeyen eleman var: {[unknown_name, *other_unknown]}")

    ground = _ground_of(netlist, reference)
    nodes = sorted(n for n in netlist.nodes() if n != ground)
    node_index = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)

    # Gerilimi bilinen dallar (bagimsiz kaynaklar + bilinmeyen direncin
    # KENDİSİ, kendi bilinmeyen degeri degil UZERINDEKI gerilim ile) -- her
    # biri KCL denklemlerine bir yardimci akim degiskeni ve KENDI satirina
    # bir V(p)-V(q)=deger denklemi ekler (standart dugum-gerilimi/MNA
    # formulasyonu -- "kaynak" kavraminin KENDISI degil, sadece bilinen bir
    # gerilim farkinin denklemlere nasil girdigi).
    voltage_branches = [
        (e.nodes[0], e.nodes[1], e.value) for e in netlist.elements if e.kind == "voltage_source"
    ]
    unknown_index = len(voltage_branches)
    voltage_branches.append((unknown.nodes[0], unknown.nodes[1], None))  # deger asagida denenir
    m = len(voltage_branches)

    resistors = [e for e in netlist.elements if e.kind == "resistor" and e.name != unknown_name]

    def solve_for_sign(signed_voltage: float) -> tuple[np.ndarray, float]:
        size = n + m
        A = np.zeros((size, size))
        b = np.zeros(size)
        for e in resistors:
            p, q = e.nodes
            g = 1.0 / e.value
            if p != ground:
                A[node_index[p], node_index[p]] += g
            if q != ground:
                A[node_index[q], node_index[q]] += g
            if p != ground and q != ground:
                A[node_index[p], node_index[q]] -= g
                A[node_index[q], node_index[p]] -= g
        for j, (p, q, value) in enumerate(voltage_branches):
            v = signed_voltage if j == unknown_index else value
            col = n + j
            if p != ground:
                A[node_index[p], col] += 1.0
                A[col, node_index[p]] += 1.0
            if q != ground:
                A[node_index[q], col] -= 1.0
                A[col, node_index[q]] -= 1.0
            b[col] = v
        try:
            x = np.linalg.solve(A, b)
        except np.linalg.LinAlgError as exc:
            raise SolverError(f"devre çözülemedi (tekil sistem): {exc}") from exc
        return x, x[n + unknown_index]

    candidates = []
    for signed_voltage in (branch_voltage_magnitude, -branch_voltage_magnitude):
        _x, current = solve_for_sign(signed_voltage)
        if current == 0:
            continue
        resistance = signed_voltage / current
        if resistance > 0:
            candidates.append(resistance)

    if len(candidates) != 1:
        raise SolverError(
            "dal geriliminin yönü belirlenemedi (iki yönde de "
            f"{'pozitif direnç bulunamadı' if not candidates else 'birden fazla pozitif sonuç çıktı'})"
        )
    return candidates[0]
