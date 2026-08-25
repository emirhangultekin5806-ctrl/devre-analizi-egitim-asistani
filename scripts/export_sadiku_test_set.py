"""Sadiku'dan otomatik 20 DC + 20 AC devre secip PNG'e render eder.

Amaç: devre-yolo-dedektor pipeline'ini (YOLO+connectivity+polarity+OCR)
şimdiye kadar hep Fiore'nin AÇIK LİSANSLI kitabında test ettik. Sadiku
(telifli, ana kaynak) hiç denenmedi. Bu script sayfaları TARAYIP "Figure
X.Y" başlıklı, gerçekten devre çizimi içeren şekilleri OTOMATİK bulur --
elle 40 figür numarası aramaya gerek yok.

DC/AC ayrımı BÖLÜM bazlı: Bölüm 2-4 (Basic Laws, Methods of Analysis,
Circuit Theorems) = solve_dc kapsamı; Bölüm 9-10 (Sinusoids and Phasors,
Sinusoidal Steady-State Analysis) = solve_ac kapsamı. Bölüm numaraları
data/processed/sadiku_full.jsonl'deki chapter_number alanından.

TELİFLİ ÇIKTI: bu script'in ürettiği PNG'ler Sadiku kitabından türetilir,
ASLA commit/paylaşım yapılmaz (bkz. CLAUDE.md, docs/kaynaklar.md) --
--out-dir varsayılanı devre-yolo-dedektor/runs/ altında (.gitignore'da).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.vision.pdf_figure import SchematicError, _captions, extract_figures, figure_bbox  # noqa: E402

DEFAULT_PDF = Path(os.environ.get("SADIKU_PDF") or r"C:\Users\Furkan\Desktop\Emirhan+\Devre analizi.pdf")

# bkz. export_figure_ground_truth.py -- aynı render ölçeği/payı.
ZOOM = 4.0  # PAD_PT artik app/vision/pdf_figure.py icinde (iki script ortak)

# (baslangic_sayfa, bitis_sayfa_haric, etiket) -- 0-indeksli, sadiku_full.jsonl'deki
# chapter_number sinirlarindan (bkz. modul docstring'i).
DC_RANGE = (60, 205, "dc")
AC_RANGE = (400, 487, "ac")


def _scan(document, start: int, end: int, limit: int) -> list[tuple[int, str]]:
    """(sayfa, "Figure X.Y") -- gercek devre cizimi bulunanlar, sayfa sirasiyla."""
    found = []
    for page_num in range(start, min(end, document.page_count)):
        if len(found) >= limit:
            break
        page = document[page_num]
        for _bbox, text in _captions(page):
            caption = text.strip()
            try:
                figures = extract_figures(page, caption)
            except SchematicError:
                continue  # bu basliktaki cizim yok (grafik/foto/tablo olabilir)
            if figures:
                found.append((page_num, caption))
    return found[:limit]


def main() -> None:
    import fitz

    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out-root", type=Path, default=Path(r"C:\Users\Furkan\Desktop\IT\devre-yolo-dedektor\runs\sadiku_test"))
    parser.add_argument("--count", type=int, default=20, help="her kategoriden kac figur")
    args = parser.parse_args()

    with fitz.open(args.pdf) as document:
        for start, end, label in (DC_RANGE, AC_RANGE):
            out_dir = args.out_root / label
            out_dir.mkdir(parents=True, exist_ok=True)
            picks = _scan(document, start, end, args.count)
            print(f"\n=== {label.upper()}: {len(picks)} figur bulundu (sayfa {start}-{end}) ===")
            for page_num, caption in picks:
                page = document[page_num]
                figures = extract_figures(page, caption)
                figure = figures[0]
                bbox = figure_bbox(figure)
                pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=fitz.Rect(*bbox))
                stem = caption.replace(" ", "_").replace(".", "_")
                png_path = out_dir / f"{stem}.png"
                pix.save(str(png_path))
                # Sayfanin DUZ metnini de yaz -- frekans/deger genelde SEKILDE
                # degil, PARAGRAFTA yaziyor (bkz. Figure 10.32 vakasi: "vs = 4
                # cos 5000t V" hicbir zaman semaya cizilmiyor). solve_from_
                # extraction.py bunu YALNIZCA kirpimda frekans bulunamayinca
                # yedek olarak kullanir (bkz. app/circuit/page_text.py).
                png_path.with_suffix(".txt").write_text(page.get_text(), encoding="utf-8")
                print(f"  s.{page_num} {caption} -> {png_path.name}")


if __name__ == "__main__":
    main()
