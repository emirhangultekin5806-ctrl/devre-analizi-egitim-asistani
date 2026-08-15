"""CLI: RAG cevap kalitesini bir regresyon seti üzerinde ölçer.

Kullanım:
    python scripts/evaluate_rag.py
    python scripts/evaluate_rag.py --case ac-enduktif-reaktans
    python scripts/evaluate_rag.py --tier fast

Neden var: prompt/model değişiklikleri bu projede birden fazla kez sessiz
gerilemeye yol açtı (örn. "örnek değer içeren cümleyi seçme" kuralı, genel
formülü de taşıyan cümleyi elediği için doğru cevabı "bulunamadı"ya
çevirmişti). Elle 3-5 soru denemek bunları yakalamıyor. Ayrıca proje
spec'i "en az 40 test senaryosu" istiyor — bu set ona doğru büyütülecek.

Vakalar: data/eval/rag_cases.json

Önkoşul: Ollama ve Chroma sunucusu çalışıyor olmalı, index kurulmuş olmalı.
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
from app.rag.generate import NOT_FOUND_MESSAGE, answer_question  # noqa: E402

CASES_PATH = ROOT / "data" / "eval" / "rag_cases.json"


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

    passed, failed = 0, []
    started = time.perf_counter()

    for case in cases:
        try:
            result = answer_question(case["question"], tier=args.tier)
            answer = result["answer"]
            elapsed = result["timings"]["total"]
        except Exception as exc:  # noqa: BLE001 - rapor et, diğer vakalara devam et
            failed.append((case["id"], [f"HATA: {type(exc).__name__}: {exc}"], ""))
            print(f"[HATA] {case['id']}: {type(exc).__name__}")
            continue

        problems = check_case(case, answer, NOT_FOUND_MESSAGE)
        if problems:
            failed.append((case["id"], problems, answer))
            print(f"[X] {case['id']} ({elapsed:.0f}s) — {'; '.join(problems)}")
        else:
            passed += 1
            print(f"[OK] {case['id']} ({elapsed:.0f}s)")

    total_time = time.perf_counter() - started
    print()
    print(f"Sonuc: {passed}/{len(cases)} gecti  ({total_time / 60:.1f} dk)")

    if failed:
        print("\n--- Basarisiz vakalar ---")
        for case_id, problems, answer in failed:
            print(f"\n{case_id}: {'; '.join(problems)}")
            if answer:
                print(f"  cevap: {answer[:220]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
