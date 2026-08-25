"""Bir kitap şeklini (VEKTÖR, doğru bilinen topoloji) raster PNG'e render eder
+ ground-truth bağlantı grafiğini JSON'a yazar.

Amaç: `devre-yolo-dedektor`'daki YENİ raster connectivity pipeline'ını
ücretsiz, otomatik bir ground-truth'a karşı doğrulamak -- elle etiketlemeye
gerek yok, zaten doğru bilinen vektör grafiği kullanılıyor. İki proje ayrı
venv'de olduğu için (bu script `fitz`/`app.vision` -- ana proje venv'i;
karşılaştırma YOLO projesinin venv'inde ayrı bir script'te) çıktı dosya
üzerinden aktarılıyor.

Kullanım:
    python scripts/export_figure_ground_truth.py --page 79 --figure "Figure 2.36" --out-dir <klasör>
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.vision.pdf_figure import extract_figures, figure_bbox  # noqa: E402
from app.vision.schematic import build_netlist  # noqa: E402

DEFAULT_PDF = Path(os.environ.get("SADIKU_PDF") or r"C:\Users\Furkan\Desktop\Emirhan+\Devre analizi.pdf")

# Render cozunurlugu -- YOLO modelinin egitildigi gorsellerle (~640px genislik
# civari kitap kirpmalari) makul olcekte olsun diye.
ZOOM = 4.0  # PAD_PT artik app/vision/pdf_figure.py icinde (iki script ortak)


def main() -> None:
    import fitz

    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--figure", required=True)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--index", type=int, default=1, help="sayfada ayni isimde birden fazla cizim varsa kacinci")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(args.pdf) as document:
        page = document[args.page]
        figures = extract_figures(page, args.figure)
        if len(figures) < args.index:
            raise SystemExit(f"{args.figure}: sayfada {len(figures)} cizim var, --index {args.index} yok")
        figure = figures[args.index - 1]

        bbox = figure_bbox(figure)
        clip = fitz.Rect(*bbox)
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip)
        stem = args.figure.replace(" ", "_").replace(".", "_")
        png_path = args.out_dir / f"{stem}.png"
        pix.save(str(png_path))

    netlist, terminals = build_netlist(figure)
    # Sembollerin PIKSEL koordinatlarını ve yön vektörünü de yaz: raster
    # tarafındaki polarite okuması (devre-yolo-dedektor/polarity.py) böylece
    # sembol sembol karşılaştırılabiliyor. PDF noktasından piksele dönüşüm
    # render'ın aynısı: clip köşesini çıkar, ZOOM ile çarp.
    symbols = [
        {
            "kind": symbol.kind,
            "box": [
                (symbol.rect[0] - clip.x0) * ZOOM,
                (symbol.rect[1] - clip.y0) * ZOOM,
                (symbol.rect[2] - clip.x0) * ZOOM,
                (symbol.rect[3] - clip.y0) * ZOOM,
            ],
            "orientation": list(symbol.orientation) if symbol.orientation else None,
        }
        for symbol in figure.symbols
    ]
    ground_truth = {
        "figure": args.figure,
        "png": str(png_path),
        "elements": [
            {"name": el.name, "kind": el.kind, "nodes": list(el.nodes)} for el in netlist.elements
        ],
        "symbols": symbols,
        "terminals": terminals,
    }
    json_path = args.out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(ground_truth, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"PNG: {png_path}")
    print(f"Ground truth: {json_path}")
    print(f"{len(netlist.elements)} eleman, {len(netlist.nodes())} dugum")
    for line in netlist.to_lines():
        print(f"  {line}")


if __name__ == "__main__":
    main()
