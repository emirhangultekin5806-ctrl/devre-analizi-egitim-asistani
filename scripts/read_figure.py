"""CLI: ders kitabındaki bir devre şeklini okuyup netlist'e çevirir ve çözer.

Kullanım:
    python scripts/read_figure.py --page 79 --figure "Figure 2.36"
    python scripts/read_figure.py --page 79 --figure "Figure 2.37" --expected 11.2

Şeklin bağlantıları PDF'in VEKTÖR verisinden geometrik olarak çıkarılır —
görsel model ya da tahmin yoktur (bkz. `app/vision/schematic.py`). `--page`
PDF'in 0'dan başlayan sayfa indeksidir (basılı sayfa numarası değil).

`--expected` verilirse sonuç kitabın basılı cevabıyla karşılaştırılır; bu,
öz-doğrulama döngüsünün "önce çöz, sonra karşılaştır" adımıdır: cevap
çözümden SONRA okunur, çözümü yönlendirmez.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.circuit.solve import (  # noqa: E402
    SolverError,
    element_results,
    power_balance,
    solve_dc,
    verify_answer,
)
from app.circuit.topology import equivalent_resistance, reduce_resistors  # noqa: E402
from app.vision.pdf_figure import extract_figures  # noqa: E402
from app.vision.schematic import build_netlist  # noqa: E402

DEFAULT_PDF = Path(r"C:\Users\Sinemis\OneDrive\Masaüstü\ilovepdf_split\Devre analizi-1.pdf")

SOURCE_KINDS = {"voltage_source", "current_source"}


def solve_with_sources(netlist) -> None:
    """Kaynaklı devre: her elemanın akım/gerilim/gücünü yazar.

    Şekilde toprak çizilmemişse bir düğüm referans seçilir — referans seçimi
    eleman büyüklüklerini değiştirmez, yalnızca düğüm gerilimlerini kaydırır.
    """
    reference = None if "gnd" in netlist.nodes() else min(netlist.nodes())
    if reference is not None:
        print(f"  (şekilde toprak yok; referans düğüm olarak {reference} seçildi)")
    try:
        solution = solve_dc(netlist, reference=reference)
    except SolverError as error:
        print(f"  Çözülemedi: {error}")
        return

    print("\nDüğüm gerilimleri:")
    for node, voltage in sorted(solution.node_voltages.items()):
        print(f"  V({node}) = {voltage:.4g} V")

    results = element_results(netlist, solution)
    print("\nEleman bazlı sonuçlar:")
    for result in results.values():
        print(f"  {result.describe()}")

    # Bağımsız tutarlılık kontrolü: harcanan güç = verilen güç.
    residual = power_balance(results)
    total = sum(abs(result.power) for result in results.values()) or 1.0
    ok = abs(residual) / total < 1e-9
    print(f"\nGüç dengesi (Tellegen): {residual:.2e} W  ->  {'tutarlı' if ok else 'TUTARSIZ'}")


def report(figure_index: int, figure, expected: float | None) -> bool:
    netlist, terminals = build_netlist(figure)

    print(f"\n--- çizim {figure_index} ---")
    print("Netlist (şekilden okundu):")
    for line in netlist.to_lines():
        print(f"  {line}")
    print(f"Dış uçlar: {terminals or '(yok)'}")

    dangling = set(netlist.dangling_nodes()) - set(terminals.values())
    if dangling:
        print(f"  UYARI: bağlanmamış düğüm(ler): {sorted(dangling)}")

    if any(element.kind in SOURCE_KINDS for element in netlist.elements):
        solve_with_sources(netlist)
        return True

    if len(terminals) != 2:
        print("  Eşdeğer direnç için iki dış uç gerekiyor — atlandı.")
        return False

    first, second = terminals.values()
    _, steps = reduce_resistors(netlist, protected_nodes=(first, second))
    if steps:
        print("İndirgeme adımları:")
        for step in steps:
            print(f"  {step.describe()}")

    computed = equivalent_resistance(netlist, first, second)
    if computed is None:
        print("  Seri/paralel ile indirgenemedi (köprü devresi olabilir).")
        return False

    names = list(terminals)
    print(f"\nR({names[0]},{names[1]}) = {computed:g} Ω")
    if expected is not None:
        ok = verify_answer(computed, expected)
        print(f"Kitabın cevabı: {expected:g} Ω  ->  {'DOĞRU' if ok else 'UYUŞMUYOR'}")
        return ok
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=int, required=True, help="0'dan başlayan sayfa indeksi")
    parser.add_argument("--figure", required=True, help='örn. "Figure 2.36"')
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--expected",
        type=float,
        default=None,
        help="kitabın basılı eşdeğer direnç cevabı (ohm); kaynaklı devrelerde kullanılmaz",
    )
    args = parser.parse_args()

    import fitz

    if not args.pdf.exists():
        raise SystemExit(f"PDF bulunamadı: {args.pdf}")

    with fitz.open(args.pdf) as document:
        page = document[args.page]
        figures = extract_figures(page, args.figure)
        print(f"{args.figure}: {len(figures)} çizim bulundu (sayfa indeksi {args.page})")
        results = [report(index, figure, args.expected) for index, figure in enumerate(figures, 1)]

    if args.expected is not None and not any(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
