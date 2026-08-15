"""CLI: baseline ("naive") RAG'ı güncel (numaralı-cümle-seçimi) mimariyle
aynı vaka setinde (`data/eval/rag_cases.json`) karşılaştırır.

Neden var: proje spec'i "baseline vs geliştirilmiş RAG sistemi
karşılaştırması" istiyor. Bu iki sistemin mimari FARKI `app/rag/generate.py`
docstring'inde anlatı olarak belgeliydi ("3 deneme sırayla elendi") ama
ÖLÇÜLMÜŞ, koşturulabilir bir karşılaştırma yoktu — bu script onu kapatır.

Kullanım:
    python scripts/compare_rag_baseline.py
    python scripts/compare_rag_baseline.py --case inj-dogum-tarihi

Önkoşul: Ollama ve Chroma sunucusu çalışıyor olmalı, index kurulmuş olmalı.
Sonuç, tabloyla birlikte `docs/rag-baseline-karsilastirmasi.md`'ye yazılır.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.evaluation.checks import check_case  # noqa: E402
from app.rag.generate import (  # noqa: E402
    NOT_FOUND_MESSAGE,
    answer_question,
    baseline_answer_question,
)

CASES_PATH = ROOT / "data" / "eval" / "rag_cases.json"
REPORT_PATH = ROOT / "docs" / "rag-baseline-karsilastirmasi.md"


def _run(pipeline, case: dict, tier: str | None) -> tuple[str, list[str], float]:
    """Bir vakayı bir pipeline ile çalıştırır. Döner: (cevap, ihlaller, süre)."""
    try:
        result = pipeline(case["question"], tier=tier)
        answer = result["answer"]
        elapsed = result["timings"]["total"]
    except Exception as exc:  # noqa: BLE001 - rapor et, diğer vakalara devam et
        return f"HATA: {type(exc).__name__}: {exc}", [f"HATA: {type(exc).__name__}"], 0.0
    return answer, check_case(case, answer, NOT_FOUND_MESSAGE), elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="Yalnızca bu id'li vakayı çalıştır")
    parser.add_argument("--tier", help="Kademeyi elle seç (fast/balanced/quality)")
    args = parser.parse_args()

    with CASES_PATH.open(encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            raise SystemExit(f"'{args.case}' id'li vaka yok.")

    rows = []
    started = time.perf_counter()
    for case in cases:
        print(f"--- {case['id']} ---")
        baseline_answer, baseline_problems, baseline_time = _run(baseline_answer_question, case, args.tier)
        print(f"  baseline    ({baseline_time:.0f}s): {'OK' if not baseline_problems else '; '.join(baseline_problems)}")
        improved_answer, improved_problems, improved_time = _run(answer_question, case, args.tier)
        print(f"  gelistirilmis ({improved_time:.0f}s): {'OK' if not improved_problems else '; '.join(improved_problems)}")
        rows.append(
            {
                "case": case,
                "baseline_answer": baseline_answer,
                "baseline_problems": baseline_problems,
                "improved_answer": improved_answer,
                "improved_problems": improved_problems,
            }
        )
    total_time = time.perf_counter() - started

    baseline_passed = sum(1 for r in rows if not r["baseline_problems"])
    improved_passed = sum(1 for r in rows if not r["improved_problems"])

    print()
    print(f"Baseline:      {baseline_passed}/{len(rows)} gecti")
    print(f"Gelistirilmis: {improved_passed}/{len(rows)} gecti")
    print(f"Toplam sure: {total_time / 60:.1f} dk")

    _write_report(rows, baseline_passed, improved_passed)
    print(f"\nRapor yazildi: {REPORT_PATH.relative_to(ROOT)}")


def _write_report(rows: list[dict], baseline_passed: int, improved_passed: int) -> None:
    lines = [
        "# Baseline vs Geliştirilmiş RAG Karşılaştırması",
        "",
        "> `scripts/compare_rag_baseline.py` ile üretildi — elle düzenlenmez, yeniden çalıştırılıp üzerine yazılır.",
        "",
        (
            "**Baseline:** tek adımlı, numaralı-cümle-seçimi güvencesi OLMADAN "
            "(`app/rag/generate.py::baseline_answer_question`) — getirilen chunk'lar doğrudan modele "
            'verilip serbestçe cevaplatılıyor. Bu, `generate.py` docstring\'inde anlatılan "2. deneme"nin '
            "(qwen2.5, tek adımlı) yeniden üretimi."
        ),
        "",
        (
            "**Geliştirilmiş:** dört adımlı güncel mimari (`answer_question`) — çeviri, numaralı-cümle-"
            "seçimi (model yalnızca NUMARA seçiyor, metin üretmiyor), sentez."
        ),
        "",
        "Retrieval (arama) İKİSİNDE DE AYNI — fark yalnızca üretim adımında, adil karşılaştırma için.",
        "",
        f"## Sonuç: Baseline {baseline_passed}/{len(rows)} — Geliştirilmiş {improved_passed}/{len(rows)}",
        "",
        "| Vaka | Beklenti | Baseline | Geliştirilmiş |",
        "|---|---|---|---|",
    ]
    for row in rows:
        case = row["case"]
        baseline_mark = "✅" if not row["baseline_problems"] else f"❌ {'; '.join(row['baseline_problems'])}"
        improved_mark = "✅" if not row["improved_problems"] else f"❌ {'; '.join(row['improved_problems'])}"
        lines.append(f"| `{case['id']}` | {case['expect']} | {baseline_mark} | {improved_mark} |")

    lines += ["", "## Baseline'ın geçtiği, geliştirilmişin kaldığı (varsa)", ""]
    regressions = [r for r in rows if not r["baseline_problems"] and r["improved_problems"]]
    if regressions:
        for row in regressions:
            lines.append(f"- `{row['case']['id']}`: {'; '.join(row['improved_problems'])}")
    else:
        lines.append("(yok)")

    lines += ["", "## Geliştirilmişin geçtiği, baseline'ın kaldığı — mimarinin asıl kazandırdığı vakalar", ""]
    improvements = [r for r in rows if r["baseline_problems"] and not r["improved_problems"]]
    if improvements:
        for row in improvements:
            case = row["case"]
            lines.append(f"### `{case['id']}`")
            lines.append(f"- Soru: {case['question']}")
            lines.append(f"- Baseline ihlalleri: {'; '.join(row['baseline_problems'])}")
            lines.append(f"- Baseline cevabı: {row['baseline_answer'][:300]}")
            lines.append("")
    else:
        lines.append("(yok)")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
