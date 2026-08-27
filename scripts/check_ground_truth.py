r"""Bir kosu raporunu elle dogrulanmis `evaluation/circuit_ground_truth.json` ile karsilastirir.

NEDEN VAR: `status == "ok"` ve `power_balance ~ 0` yalnizca IC TUTARLILIK
gosterir, cevabin DOGRU oldugunu degil. OLCULDU (2026-08-26): 1-100/65.png'de
sekildeki 6 direncin yalnizca 2'si bulundugu halde devre "cozuldu" ve guc
dengesi tuttu; 1-100/31.png'de 9 degerin 9'u dogru okundu ama karsilikli
enduktans (j1200 Ω) modellenmedigi icin cevap yine yanlisti.

Karsilastirma ELEMAN ADIYLA degil, tur basina DEGER COKLUGU ile yapilir --
"resistor5" adi kosudan kosuya kayiyor, sekilde yazan 7500 Ω kaymiyor.

Kullanim:
    .venv\Scripts\python scripts\check_ground_truth.py runs_regression_fix1.json

Cikis kodu: uyusmayan devre varsa 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GROUND_TRUTH = REPO / "evaluation" / "circuit_ground_truth.json"
# Deger okumada kabul edilen bagil sapma. OCR/VLM 7500 yerine 7.5k yazabilir
# ama 7500 yerine 750 yazmasi HATADIR -- esik bu ikisini ayiracak kadar dar.
TOLERANCE = 0.01

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")


def _match(expected: list[float], actual: list[float]) -> tuple[list[float], list[float]]:
    """(bulunamayan beklenenler, beklenmeyen fazlalar) -- toleransli coklu eslesme."""
    remaining = list(actual)
    missing = []
    for want in expected:
        hit = next(
            (got for got in remaining if abs(got - want) <= TOLERANCE * max(abs(want), 1e-12)),
            None,
        )
        if hit is None:
            missing.append(want)
        else:
            remaining.remove(hit)
    return missing, remaining


def compare(truth: dict, report_entry: dict) -> list[str]:
    """Bu devre icin sorun listesi -- bos liste "dogru" demektir."""
    solved = report_entry.get("status") == "ok"
    if truth["verdict"] == "out_of_scope":
        if solved:
            return [f"KAPSAM DISI oldugu halde cozuldu -- {truth.get('sebep', '')}"]
        return []
    if not solved:
        return []  # cozulememek yanlis cevap degil; regression_44.py'nin isi

    actual: dict[str, list[float]] = {}
    for element in report_entry["elements"]:
        actual.setdefault(element["kind"], []).append(float(element["value"]))

    problems = []
    for kind, expected in truth["components"].items():
        missing, extra = _match(list(expected), actual.get(kind, []))
        if missing:
            problems.append(f"{kind}: sekilde var, cozumde YOK -> {missing}")
        if extra:
            problems.append(f"{kind}: cozumde var, sekilde YOK -> {extra}")
    for kind in set(actual) - set(truth["components"]):
        problems.append(f"{kind}: sekilde hic yok, cozumde var -> {actual[kind]}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH)
    args = parser.parse_args()

    truths = {k: v for k, v in json.loads(args.ground_truth.read_text(encoding="utf-8")).items()
              if not k.startswith("_")}
    report = json.loads(args.report.read_text(encoding="utf-8"))

    checked = wrong = 0
    for stem, truth in sorted(truths.items()):
        entry = report.get(stem)
        if entry is None:
            continue
        checked += 1
        problems = compare(truth, entry)
        if problems:
            wrong += 1
            print(f"{stem}: YANLIS")
            for problem in problems:
                print(f"    {problem}")
        else:
            durum = "cozuldu" if entry.get("status") == "ok" else "cozulemedi (dogru davranis)"
            print(f"{stem}: dogru ({durum})")

    print(f"\n{checked - wrong}/{checked} devre elle dogrulanmis cevapla uyusuyor")
    raise SystemExit(1 if wrong else 0)


if __name__ == "__main__":
    main()
