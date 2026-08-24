"""extract_circuit'in hata yollarını gerçek YOLO/subprocess çağırmadan
doğrular -- gerçek çağrı ayrı bir venv + ağırlık dosyası ister, burada
sadece koruma mantığı (venv yok/ağırlık yok/subprocess başarısız/çıktı
üretilmedi) test edilir.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from app.vision import pipeline_bridge as pb


def test_missing_venv_raises_bridge_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "YOLO_PYTHON", tmp_path / "does_not_exist" / "python.exe")
    with pytest.raises(pb.PipelineBridgeError, match="venv'i bulunamadı"):
        pb.extract_circuit(tmp_path / "img.png", tmp_path / "out")


def test_missing_weights_raises_bridge_error(tmp_path, monkeypatch):
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    monkeypatch.setattr(pb, "YOLO_PYTHON", fake_python)
    monkeypatch.setattr(pb, "YOLO_WEIGHTS", tmp_path / "does_not_exist.pt")
    with pytest.raises(pb.PipelineBridgeError, match="ağırlıkları bulunamadı"):
        pb.extract_circuit(tmp_path / "img.png", tmp_path / "out")


def _stub_ok_deps(tmp_path, monkeypatch):
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    fake_weights = tmp_path / "best.pt"
    fake_weights.write_bytes(b"")
    monkeypatch.setattr(pb, "YOLO_PYTHON", fake_python)
    monkeypatch.setattr(pb, "YOLO_WEIGHTS", fake_weights)


def test_nonzero_exit_raises_bridge_error_with_stderr(tmp_path, monkeypatch):
    _stub_ok_deps(tmp_path, monkeypatch)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="YOLO patladı")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(pb.PipelineBridgeError, match="YOLO patladı"):
        pb.extract_circuit(tmp_path / "img.png", tmp_path / "out")


def test_missing_extraction_json_raises_bridge_error(tmp_path, monkeypatch):
    _stub_ok_deps(tmp_path, monkeypatch)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(pb.PipelineBridgeError, match="üretilmedi"):
        pb.extract_circuit(tmp_path / "img.png", tmp_path / "out")


def test_success_returns_parsed_extraction_json(tmp_path, monkeypatch):
    _stub_ok_deps(tmp_path, monkeypatch)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    payload = {"image": "x.png", "components": {}, "warnings": [], "net_count": 0}
    (out_dir / "extraction.json").write_text(json.dumps(payload), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert pb.extract_circuit(tmp_path / "img.png", out_dir) == payload
