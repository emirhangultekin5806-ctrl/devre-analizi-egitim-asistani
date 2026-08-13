"""Çevre (mesh/loop) analizi — KVL tabanlı BAĞIMSIZ çözüm yöntemi.

Neden var: aynı devreyi farklı bir yöntemle çözüp sonuçları karşılaştırmak
için. `solve.py` (ngspice) düğüm analizi yapar — KCL tabanlı, bilinmeyenler
düğüm gerilimleri. Bu modül çevre analizi yapar — KVL tabanlı, bilinmeyenler
çevre akımları. İki yöntem farklı denklem sistemleri kurar; aynı sonuca
varmaları güçlü bir çapraz doğrulamadır ve **kitabın cevabına ihtiyaç
duymaz**.

Ders kitabının öğrettiği iki yöntem de bunlar olduğu için, ileride öğrenciye
"aynı devreyi iki yöntemle de çözelim" diye gösterilebilir.

Yöntem:
1. Devre grafiğinde bir kapsayan ağaç (spanning tree) bulunur.
2. Ağaca girmeyen her eleman bir temel çevre (fundamental loop) tanımlar:
   o eleman + ağaç üzerinden geri dönen yol. Çevre sayısı = e - n + 1.
3. Her çevre için KVL yazılır; bilinmeyenler çevre akımlarıdır.
4. Doğrusal sistem çözülür; eleman akımı, o elemandan geçen çevre
   akımlarının işaretli toplamıdır.

Kapsam: dirençler + DC gerilim ve akım kaynakları.

**Süpermesh.** Klasik çevre analizinde iki çevrenin paylaştığı bir akım
kaynağı "süpermesh" gerektirir (iki çevreyi birleştir, ayrıca kısıt
denklemi yaz). Burada bu, ağaç seçimiyle kendiliğinden çözülüyor: kapsayan
ağaç akım kaynaklarını dışarıda bırakacak şekilde kurulduğu için her akım
kaynağı kendi temel çevresini tanımlar ve o çevrenin akımı doğrudan
bilinir. Bilinen çevre akımlarının katkısı denklemin sağ tarafına geçer,
yalnızca kalan bilinmeyenler için sistem çözülür.
"""

from app.circuit.netlist import Element, Netlist


class MeshAnalysisError(RuntimeError):
    """Çevre analizi bu devreye uygulanamadı."""


def _spanning_tree(netlist: Netlist) -> tuple[list[Element], dict[str, list[tuple[str, Element]]]]:
    """Kapsayan ağacı ve komşuluk listesini döndürür.

    Akım kaynakları BİLEREK ağacın dışında bırakılır (önce diğer elemanlarla
    ağaç kurulur). Böylece her akım kaynağı kendi temel çevresini tanımlar ve
    o çevrenin akımı doğrudan bilinir — süpermesh'in klasik "iki çevreyi
    birleştir + kısıt denklemi yaz" işlemi bu seçimle kendiliğinden çözülür.
    """
    adjacency: dict[str, list[tuple[str, Element]]] = {n: [] for n in netlist.nodes()}
    for element in netlist.elements:
        a, b = element.nodes
        adjacency[a].append((b, element))
        adjacency[b].append((a, element))

    start = next(iter(sorted(netlist.nodes())))
    visited = {start}
    tree: list[Element] = []

    # İki geçiş: önce akım kaynağı olmayanlarla ağacı büyüt, sonra
    # (zorunlu kalırsa) akım kaynaklarıyla tamamla.
    for allow_current_sources in (False, True):
        changed = True
        while changed:
            changed = False
            # list() ZORUNLU: döngü içinde `visited` büyüyor, küme üzerinde
            # doğrudan dönmek "set changed size during iteration" verir.
            for node in list(visited):  # noqa: PERF101
                for neighbour, element in adjacency[node]:
                    if neighbour in visited:
                        continue
                    if not allow_current_sources and element.kind == "current_source":
                        continue
                    visited.add(neighbour)
                    tree.append(element)
                    changed = True

    if visited != netlist.nodes():
        raise MeshAnalysisError(
            f"Devre bağlantısız: {sorted(netlist.nodes() - visited)} düğümlerine ulaşılamıyor"
        )
    return tree, adjacency


def _tree_path(
    start: str, goal: str, tree: list[Element]
) -> list[tuple[Element, int]]:
    """Ağaç üzerinde `start`→`goal` yolu; her adım (eleman, yön) olarak.

    Yön: elemanı nodes[0]→nodes[1] geçiyorsak +1, tersiyse -1.
    """
    adjacency: dict[str, list[tuple[str, Element]]] = {}
    for element in tree:
        a, b = element.nodes
        adjacency.setdefault(a, []).append((b, element))
        adjacency.setdefault(b, []).append((a, element))

    previous: dict[str, tuple[str, Element]] = {}
    visited = {start}
    queue = [start]
    while queue:
        node = queue.pop(0)
        if node == goal:
            break
        for neighbour, element in adjacency.get(node, []):
            if neighbour not in visited:
                visited.add(neighbour)
                previous[neighbour] = (node, element)
                queue.append(neighbour)

    path: list[tuple[Element, int]] = []
    node = goal
    while node != start:
        parent, element = previous[node]
        direction = 1 if element.nodes == (parent, node) else -1
        path.append((element, direction))
        node = parent
    path.reverse()
    return path


def find_loops(netlist: Netlist) -> list[list[tuple[Element, int]]]:
    """Temel çevreleri döndürür: her biri (eleman, yön) listesidir."""
    tree, _ = _spanning_tree(netlist)
    tree_set = {id(e) for e in tree}

    loops = []
    for element in netlist.elements:
        if id(element) in tree_set:
            continue
        a, b = element.nodes
        # Çevre: elemanı a→b geç, sonra ağaç üzerinden b→a dön.
        loop: list[tuple[Element, int]] = [(element, 1)]
        loop.extend(_tree_path(b, a, tree))
        loops.append(loop)
    return loops


def solve_mesh(netlist: Netlist) -> dict[str, float]:
    """Çevre analiziyle eleman akımlarını çözer.

    Dönen: {eleman_adı: akım}. Akım işareti, elemanın `nodes[0]→nodes[1]`
    yönünde pozitiftir.
    """
    import numpy as np

    unsupported = {e.kind for e in netlist.elements} - {
        "resistor",
        "voltage_source",
        "current_source",
    }
    if unsupported:
        raise MeshAnalysisError(f"Desteklenmeyen eleman türü: {sorted(unsupported)}")
    if any(e.value is None for e in netlist.elements):
        raise MeshAnalysisError("Değeri verilmemiş eleman var")

    loops = find_loops(netlist)
    if not loops:
        raise MeshAnalysisError("Devrede kapalı çevre yok")

    # Akım kaynağı ağacın dışında bırakıldığı için (bkz. _spanning_tree)
    # onun tanımladığı çevrenin akımı doğrudan bilinir: süpermesh kısıtı.
    known: dict[int, float] = {}
    for index, loop in enumerate(loops):
        link, sign = loop[0]  # temel çevrenin ilk elemanı ağaç dışı olandır
        if link.kind == "current_source":
            known[index] = sign * link.value

    unknown = [i for i in range(len(loops)) if i not in known]
    if not unknown:
        loop_currents = np.array([known.get(i, 0.0) for i in range(len(loops))])
    else:
        impedance = np.zeros((len(unknown), len(unknown)))
        voltages = np.zeros(len(unknown))

        def coupling(loop_a, loop_b) -> float:
            signs_b = {id(e): s for e, s in loop_b}
            return sum(
                sign * signs_b[id(element)] * element.value
                for element, sign in loop_a
                if element.kind == "resistor" and id(element) in signs_b
            )

        for row, i in enumerate(unknown):
            for column, j in enumerate(unknown):
                impedance[row][column] = coupling(loops[i], loops[j])
            for element, sign in loops[i]:
                if element.kind == "voltage_source":
                    # nodes = (+, -). Çevre elemanı +→- geçiyorsa gerilim
                    # düşüşü +V'dir; KVL'de karşı tarafa geçince işaret döner.
                    voltages[row] -= sign * element.value
            # Bilinen (akım kaynağı) çevre akımlarının katkısı sağ tarafa geçer.
            for j, value in known.items():
                voltages[row] -= coupling(loops[i], loops[j]) * value

        try:
            solved = np.linalg.solve(impedance, voltages)
        except np.linalg.LinAlgError as exc:
            raise MeshAnalysisError(f"Denklem sistemi çözülemedi: {exc}") from exc

        loop_currents = np.zeros(len(loops))
        for row, i in enumerate(unknown):
            loop_currents[i] = solved[row]
        for i, value in known.items():
            loop_currents[i] = value

    currents: dict[str, float] = {}
    for element in netlist.elements:
        total = 0.0
        for index, loop in enumerate(loops):
            for member, sign in loop:
                if member is element:
                    total += sign * loop_currents[index]
        currents[element.name] = float(total)
    return currents
