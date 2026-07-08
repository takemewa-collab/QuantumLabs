"""QuantumLabs — Eval karsilastirma / regresyon gate'i.

Aday raporu (yeni prompt/model) baseline'a kiyaslar. REGRESYON = baseline'da GECEN
bir gorevin adayda KALMASI. Ozet metrik delta'lari + regresyon listesi basar.

Cikis kodu (insan-onayli promotion sinyali):
    0 -> regresyon yok (promote'a aday; yine de insan onaylar)
    1 -> regresyon var / pass_rate dustu -> PROMOTE ETME (once incele)

Kullanim:
    python -m eval.compare eval/reports/<baseline>.json eval/reports/<cand>.json
"""
from __future__ import annotations

import argparse
import json
import sys


def _by_id(report):
    return {r["id"]: r for r in report.get("results", [])}


def compare_reports(baseline: dict, candidate: dict) -> int:
    base, cand = _by_id(baseline), _by_id(candidate)
    bs, cs = baseline.get("summary", {}), candidate.get("summary", {})

    print("\n" + "=" * 66)
    print(f"KIYAS  baseline={baseline.get('label')} ({baseline.get('model')})")
    print(f"       aday    ={candidate.get('label')} ({candidate.get('model')})")
    print("=" * 66)
    for k in ["pass_rate", "avg_score", "avg_steps", "tool_error_rate", "p50_latency_s"]:
        b, c = bs.get(k, 0), cs.get(k, 0)
        d = round(c - b, 3)
        arrow = "→" if d == 0 else ("↑" if d > 0 else "↓")
        print(f"  {k:<18} {b:>8}  ->  {c:>8}   ({arrow} {d:+})")

    # Gorev-bazli gecis/dususler
    regressions, fixes = [], []
    for tid in sorted(set(base) & set(cand)):
        bp, cp = base[tid]["passed"], cand[tid]["passed"]
        if bp and not cp:
            regressions.append(tid)
        elif not bp and cp:
            fixes.append(tid)

    print("-" * 66)
    if fixes:
        print(f"  DUZELEN ({len(fixes)}): {', '.join(fixes)}")
    if regressions:
        print(f"  REGRESYON ({len(regressions)}): {', '.join(regressions)}")
    else:
        print("  REGRESYON: yok")
    print("=" * 66)

    pass_dropped = cs.get("pass_rate", 0) < bs.get("pass_rate", 0)
    if regressions or pass_dropped:
        print("SONUC: ✗ PROMOTE ETME — regresyon/pass-rate dususu var, once incele.")
        return 1
    print("SONUC: ✓ regresyon yok — promote'a aday (insan onayi ile).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="eval baseline vs aday kiyas")
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    args = ap.parse_args(argv)
    with open(args.baseline, encoding="utf-8") as f:
        base = json.load(f)
    with open(args.candidate, encoding="utf-8") as f:
        cand = json.load(f)
    return compare_reports(base, cand)


if __name__ == "__main__":
    sys.exit(main())
