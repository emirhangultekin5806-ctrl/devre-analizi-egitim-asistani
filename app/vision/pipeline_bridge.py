"""Kullanıcının yüklediği devre fotoğrafını GERÇEK pipeline (YOLO+connectivity+
OCR, `devre-yolo-dedektor` reposu) ile işler.

Neden subprocess: bu repo (PySpice/ngspice) ile `devre-yolo-dedektor`
(ultralytics/cv2/skimage) AYRI venv'lerde -- bkz. `scripts/solve_from_extraction.py`
docstring'i, CLAUDE.md. Streamlit bu venv'de çalışıyor, diğerinin
paketlerine erişemiyor -- `extract_for_solve.py`'yi diğer venv'in python'uyla
subprocess olarak çalıştırıp `extraction.json`'ı okuyoruz. CLI toplu koşumun
(`batch_extract.py` + `scripts/solve_from_extraction.py`) YAPTIĞI AYNI
köprülemeyi UI'dan tetikliyoruz -- yeni bir mimari değil, var olanın UI'a
bağlanması.

BULUNDU (2026-08-21 denetimi): bu köprü hiç yoktu -- "Kendi Devreni Yükle"
ekranı hâlâ eski `read_circuit_image` (bütün görüntüyü VLM'e verip
TOPOLOJİYİ de ona kurdurma) yolunu kullanıyordu; o yolun halüsinasyon
riski `read_component_value`'nun (sadece DEĞER okuyan, topolojiyi YOLO'dan
alan) çözdüğü zaafın AYNISI (bkz. `vlm_read.py` docstring'i, Figure 2.8
örneği: VLM değeri doğru okurken tek bir direnci iki hayali direnç sandı).
Bu modül o zaafı taşımıyor -- topoloji YOLO'dan gelir, VLM sadece değer okur.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

_THIS_REPO = Path(__file__).resolve().parent.parent.parent
YOLO_REPO = _THIS_REPO.parent / "devre-yolo-dedektor"
YOLO_PYTHON = YOLO_REPO / ".venv" / "Scripts" / "python.exe"
YOLO_WEIGHTS = YOLO_REPO / "runs" / "detect" / "deneme18" / "weights" / "best.pt"
EXTRACT_TIMEOUT_SECONDS = 180


class PipelineBridgeError(RuntimeError):
    """YOLO/connectivity yan-süreci çalıştırılamadı ya da beklenmedik çıktı verdi."""


def extract_circuit(image_path: Path, out_dir: Path, conf: float = 0.45) -> dict:
    """Verilen görüntüyü YOLO+connectivity+OCR pipeline'ından geçirir.

    Dönen: `extract_for_solve.py`'nin ürettiği extraction.json içeriği --
    `{"image", "components": {ad: {"kind","nets","crop","ocr_value_hint",
    "control_label_hint"}}, "warnings", "net_count"}` (bkz. o script).
    `scripts.solve_from_extraction.solve_extraction`'a doğrudan verilebilir.

    Ayrı venv'de subprocess olarak çalışır -- bu venv'in kendisinde
    ultralytics/cv2 kurulu OLMAYABİLİR (bilerek, bkz. modül docstring'i).
    """
    if not YOLO_PYTHON.exists():
        raise PipelineBridgeError(
            f"devre-yolo-dedektor venv'i bulunamadı: {YOLO_PYTHON} -- "
            "o repo kurulu değil ya da farklı bir yerde."
        )
    if not YOLO_WEIGHTS.exists():
        raise PipelineBridgeError(f"YOLO ağırlıkları bulunamadı: {YOLO_WEIGHTS}")

    # image_path/out_dir MUTLAK verilmeli -- subprocess `cwd=YOLO_REPO` ile
    # calisiyor, extract_for_solve.py --out-dir'i KENDI cwd'sine gore
    # (Path.resolve()) coziyor. GERCEK CAGRIDA YAKALANDI (2026-08-21): goreli
    # bir out_dir verilince extraction.json BEKLENEN yerde degil,
    # YOLO_REPO/<out_dir> altinda olusuyordu, "uretilmedi" hatasi yanlislikla
    # firliyordu -- dosya aslinda vardi, sadece BASKA bir yerde.
    try:
        result = subprocess.run(
            [
                str(YOLO_PYTHON), "extract_for_solve.py",
                "--image", str(image_path.resolve()),
                "--weights", str(YOLO_WEIGHTS),
                "--out-dir", str(out_dir.resolve()),
                "--conf", str(conf),
            ],
            cwd=str(YOLO_REPO),
            capture_output=True,
            text=True,
            timeout=EXTRACT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineBridgeError(
            f"YOLO/connectivity {EXTRACT_TIMEOUT_SECONDS}s içinde bitmedi -- görüntü çok mu büyük?"
        ) from exc

    if result.returncode != 0:
        raise PipelineBridgeError(
            f"Görüntü işlenemedi (YOLO/connectivity):\n{(result.stderr or result.stdout).strip()}"
        )

    extraction_path = out_dir / "extraction.json"
    if not extraction_path.exists():
        raise PipelineBridgeError("extraction.json üretilmedi -- beklenmeyen bir hata oldu.")
    return json.loads(extraction_path.read_text(encoding="utf-8"))
