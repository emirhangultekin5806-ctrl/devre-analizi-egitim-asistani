"""`devre-yolo-dedektor/batch_extract.py` ciktisindaki TUM extraction.json'lari
sirayla cozer, sonuclari tek bir JSON raporunda toplar.

Tek surecte kalir (subprocess-basina degil) -- 100+ figurluk kosuda Python
baslatma yukunu (VLM cagrisi yaninda kucuk ama toplamda anlamli) tekrar
tekrar odemez.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.solve_from_extraction import SolveFromExtractionError, solve_extraction  # noqa: E402

# Windows konsolu varsayilan olarak cp1254/cp1252 kullanir -- gercek devre
# verisinde gecen Yunan harfleri (orn. bagimli kaynak kontrol degiskeni
# "i_delta") bu kod sayfasinda YOK, print() UnicodeEncodeError ile COKUYOR
# ve 100+ figurluk butun kosum yarida kesiliyor (rapor dosyasi zaten
# ensure_ascii=False ile UTF-8 yazildigi icin etkilenmiyordu, sadece konsol
# ciktisi coktu). BULUNDU: 2026-08-24, real_screenshots_50 kosusunda.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-root", required=True, help="batch_extract.py'nin --out-root'u")
    parser.add_argument("--report", required=True, help="ozet JSON'un yazilacagi yol")
    args = parser.parse_args()

    root = Path(args.extract_root)
    extraction_files = sorted(root.glob("*/extraction.json"))
    report = {}
    report_path = Path(args.report)

    for i, ef in enumerate(extraction_files):
        stem = ef.parent.name
        data = json.loads(ef.read_text(encoding="utf-8"))
        t0 = time.time()
        try:
            out = solve_extraction(data, reference="n0", verbose=False)
            report[stem] = {
                "status": "ok",
                "elements": out["elements"],
                # abs(): DC'de zaten reel float, AC'de karmaşık -- json
                # karmaşık sayı yazamaz, "0'a ne kadar yakın" kontrolü için
                # zaten büyüklük yeterli (bkz. solve_from_extraction.py'deki
                # ok=... kontrolü de aynı şekilde abs() kullanıyor).
                "power_balance": abs(out["power_balance"]),
                "seconds": round(time.time() - t0, 1),
            }
            print(f"[{i+1}/{len(extraction_files)}] {stem}: OK ({report[stem]['seconds']}s)")
        except SolveFromExtractionError as exc:
            report[stem] = {"status": "fail", "reason": str(exc), "seconds": round(time.time() - t0, 1)}
            print(f"[{i+1}/{len(extraction_files)}] {stem}: FAIL -- {exc}")
        except Exception as exc:  # beklenmeyen hata da toplu kosumu durdurmasin
            report[stem] = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
            print(f"[{i+1}/{len(extraction_files)}] {stem}: BEKLENMEYEN HATA -- {exc}")

        # Her adimda yaz -- uzun kosum yarida kesilirse (VLM/Ollama coker,
        # zaman asimi) o ana kadarki sonuclar KAYBOLMASIN.
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = sum(1 for r in report.values() if r["status"] == "ok")
    print(f"\n{ok}/{len(report)} basarili -> {report_path}")


if __name__ == "__main__":
    main()
