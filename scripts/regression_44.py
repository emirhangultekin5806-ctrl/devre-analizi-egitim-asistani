r"""44 gercek devre fotografi uzerinde uctan uca regresyon kosusu.

NEDEN VAR: 2026-08-26'da deger okuma yolunu degistiren 8 commit, 448 birim
testi + 4 devreyle dogrulanip "bitti" denerek atildi. Ayni gun bu set
kosuldugunda cozulen devre sayisi 15 -> 6'ya dusmustu. Birim testleri
"yazdigim kod yazdigim gibi calisiyor mu" sorusunu cevaplar; "bu degisiklik
kac gercek devreyi kirdi" sorusunu YALNIZCA bu set cevaplar.

Kullanim:
    .venv\Scripts\python scripts\regression_44.py            # kos + karsilastir
    .venv\Scripts\python scripts\regression_44.py --promote  # sonucu yeni baseline yap

Cikis kodu: bozulan devre varsa 1, yoksa 0.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vision.pipeline_bridge import (
    YOLO_PYTHON,
    YOLO_REPO,
    YOLO_WEIGHTS,
)

REPO = Path(__file__).resolve().parent.parent
IMAGE_LIST = YOLO_REPO / "run_noopamp_list.txt"
BASELINE = REPO / "evaluation" / "regression_44_baseline.json"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")


def _run(cmd: list[str], cwd: Path, log: Path) -> None:
    """Alt sureci calistir, ciktisini log'a yaz; basarisizsa DURDUR.

    Sessizce devam etmek, yarim extraction uzerinden "regresyon yok" raporu
    uretir -- olculmemis seyi olculmus gibi gostermek bu script'in onlemeye
    calistigi seyin ta kendisi.
    """
    with log.open("w", encoding="utf-8", errors="backslashreplace") as handle:
        result = subprocess.run(
            cmd, cwd=str(cwd), stdout=handle, stderr=subprocess.STDOUT, check=False
        )
    if result.returncode != 0:
        raise SystemExit(f"BASARISIZ ({result.returncode}): {' '.join(cmd)}\n  log: {log}")


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(bozulan, duzelen) devre listeleri -- yalnizca IKISINDE de olan devreler."""
    shared = baseline.keys() & current.keys()
    broke = sorted(s for s in shared if baseline[s]["status"] == "ok" and current[s]["status"] != "ok")
    fixed = sorted(s for s in shared if baseline[s]["status"] != "ok" and current[s]["status"] == "ok")
    return broke, fixed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--tag", default=time.strftime("%m%d_%H%M"), help="cikti dosyalarinin eki")
    parser.add_argument("--promote", action="store_true", help="kosu sonucunu yeni baseline yap")
    parser.add_argument("--skip-extract", action="store_true", help="varolan extraction'lari yeniden kullan")
    args = parser.parse_args()

    if not IMAGE_LIST.exists():
        raise SystemExit(f"Goruntu listesi yok: {IMAGE_LIST}")
    if not YOLO_WEIGHTS.exists():
        raise SystemExit(f"YOLO agirliklari yok: {YOLO_WEIGHTS}")

    out_root = YOLO_REPO / "runs" / f"regression_{args.tag}_extract"
    report = REPO / f"runs_regression_{args.tag}.json"

    if not args.skip_extract:
        print(f"[1/2] extraction -> {out_root}")
        _run(
            [
                str(YOLO_PYTHON), "batch_extract.py",
                "--list", str(IMAGE_LIST),
                "--weights", str(YOLO_WEIGHTS),
                "--out-root", str(out_root),
            ],
            cwd=YOLO_REPO,
            log=REPO / f"runs_regression_{args.tag}_extract.log",
        )

    print(f"[2/2] solve -> {report}")
    _run(
        [
            sys.executable, "scripts/batch_solve.py",
            "--extract-root", str(out_root),
            "--report", str(report),
        ],
        cwd=REPO,
        log=REPO / f"runs_regression_{args.tag}_solve.log",
    )

    current = json.loads(report.read_text(encoding="utf-8"))
    ok = sum(1 for v in current.values() if v["status"] == "ok")

    if not args.baseline.exists():
        print(f"\nBaseline yok ({args.baseline}). Bu kosu: {ok}/{len(current)} cozuldu.")
        print("Kabul ediyorsan --promote ile baseline yap.")
        return

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    base_ok = sum(1 for v in baseline.values() if v["status"] == "ok")
    broke, fixed = compare(baseline, current)

    print(f"\nESKI {base_ok}/{len(baseline)} -> YENI {ok}/{len(current)}")
    print(f"DUZELEN {len(fixed)}: {fixed}")
    print(f"BOZULAN {len(broke)}: {broke}")
    for stem in broke:
        print(f"  {stem}: {current[stem].get('reason', '')[:110]}")

    if args.promote:
        shutil.copyfile(report, args.baseline)
        print(f"\nBaseline guncellendi: {args.baseline}")

    # "Cozulen sayisi ARTTI" tek basina yeterli degil: 3 kazanip 12 kaybetmek
    # de toplam dususu gizleyebilir, bu yuzden olcut BOZULAN sayisi.
    raise SystemExit(1 if broke else 0)


if __name__ == "__main__":
    main()
