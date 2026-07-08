"""QuantumLabs — Eval harness: gorev setini agent'la kosar, judge'lar, rapor yazar.

Self-improvement cark'inin OLCUM zemini. Her degisiklikte (prompt/model/kod) kosar;
pass-rate / adim / tool-hata / latency trendini uretir. Baseline'a kiyaslamak icin
eval/compare.py kullanilir (insan-onayli promotion gate'i).

REPRODUKSIYON: eval izole bir session workspace'inde kosar (transcript/memory oraya
gider, gercek repo'yu KIRLETMEZ); memory + profil enjeksiyonu KAPALI -> cekirdek
yetenegi olcer, gecmis/profil gurultusu skoru sapt(ir)maz. cwd = repo (dosya
araclari gercek repoda okur). Yalniz SALT-OKUNUR gorevler (repo'yu degistirmez).

Kullanim:
    python -m eval.harness --label baseline
    python -m eval.harness --label cand --model efeacil/qwen3-4b-quantum-v2 --limit 3
    python -m eval.harness --baseline eval/reports/<baseline>.json --label cand   # kosar + kiyaslar
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import sys
import tempfile
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.code_agent import run_agent
from agents.llm import default_config, quantum_pod_config
from protocols.safety import AutoApprover
from runtime.session import Session
from runtime.transcript import _TRANSCRIPT_SUBDIR
from eval import judge as judge_mod

_REPORTS_DIR = os.path.join(_REPO_ROOT, "eval", "reports")
_DEFAULT_TASKS = os.path.join(_REPO_ROOT, "eval", "tasks.jsonl")


def _load_dotenv(path):
    """.env'i os.environ'a yukle (zaten set olani EZMEZ). api/main.py ile ayni
    desen — eval api'yi IMPORT ETMEDEN kostugu icin pod env'ini buradan okuruz;
    yoksa QUANTUM_POD_* gorunmez, eval yanlislikla yerel default modele duser."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k and k not in os.environ:
                    os.environ[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass


def _model_config(model_override):
    """Pod env varsa pod, yoksa default; --model verilirse model id'yi ez."""
    if os.getenv("QUANTUM_POD_BASE_URL") and os.getenv("QUANTUM_POD_API_KEY"):
        cfg = quantum_pod_config()
    else:
        cfg = default_config()
    if model_override:
        cfg = dataclasses.replace(cfg, model=model_override)
    return cfg


def _load_tasks(path):
    tasks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tasks.append(json.loads(line))
    return tasks


def _transcript_metrics(workspace, session_id):
    """Izole transcript'ten adim/tool-cagrisi/tool-hata say."""
    path = os.path.join(workspace, _TRANSCRIPT_SUBDIR, f"{session_id}.jsonl")
    steps = tool_calls = tool_errors = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                t = ev.get("type")
                if t == "assistant":
                    steps += 1
                elif t == "observation":
                    tool_calls += 1
                    if ev.get("ok") is False:
                        tool_errors += 1
    except OSError:
        pass
    return {"steps": steps, "tool_calls": tool_calls, "tool_errors": tool_errors}


def run_task(task, cfg):
    """Tek gorevi izole koş, judge'la. Donus: sonuc sozlugu."""
    tmp = tempfile.mkdtemp(prefix="ql-eval-")
    session = Session(tmp, model_config=cfg)
    t0 = time.time()
    error = None
    answer = None
    try:
        answer = run_agent(
            task["prompt"],
            max_steps=task.get("max_steps", 6),
            approver=AutoApprover(approve=True),
            session=session,
            workspace=_REPO_ROOT,          # cwd = repo (dosya araclari); transcript -> tmp
            memory_injection=False,        # reprodüksiyon: gecmis enjekte etme
            profile_injection=False,       # reprodüksiyon: profil enjekte etme
        )
    except Exception as ex:  # noqa: BLE001 — bir gorev cokerse eval devam etsin
        error = f"{type(ex).__name__}: {ex}"
    latency = round(time.time() - t0, 1)
    metrics = _transcript_metrics(tmp, session.session_id)
    verdict = judge_mod.score(task, answer)
    # tmp temizle (transcript/memory ephemeral)
    try:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    return {
        "id": task["id"], "category": task.get("category", ""),
        "prompt": task["prompt"],
        "answer": (answer or "")[:1000],
        "score": verdict["score"], "passed": verdict["passed"],
        "reason": verdict["reason"],
        "latency_s": latency, "error": error,
        **metrics,
    }


def _summarize(results):
    n = len(results) or 1
    passed = sum(1 for r in results if r["passed"])
    lat = sorted(r["latency_s"] for r in results)
    p50 = lat[len(lat) // 2] if lat else 0
    total_calls = sum(r["tool_calls"] for r in results)
    total_errs = sum(r["tool_errors"] for r in results)
    return {
        "n": len(results),
        "pass_rate": round(passed / n, 3),
        "avg_score": round(sum(r["score"] for r in results) / n, 3),
        "avg_steps": round(sum(r["steps"] for r in results) / n, 2),
        "tool_error_rate": round(total_errs / total_calls, 3) if total_calls else 0.0,
        "p50_latency_s": p50,
    }


def _print_report(report):
    s = report["summary"]
    print("\n" + "=" * 66)
    print(f"EVAL RAPORU  label={report['label']}  model={report['model']}")
    print("=" * 66)
    print(f"{'id':<20} {'cat':<14} {'score':>5} {'pass':>5} {'steps':>5} {'lat':>5}")
    print("-" * 66)
    for r in report["results"]:
        mark = "✓" if r["passed"] else "✗"
        print(f"{r['id']:<20} {r['category']:<14} {r['score']:>5} {mark:>5} "
              f"{r['steps']:>5} {r['latency_s']:>5}")
    print("-" * 66)
    print(f"pass_rate={s['pass_rate']}  avg_score={s['avg_score']}  "
          f"avg_steps={s['avg_steps']}  tool_err={s['tool_error_rate']}  "
          f"p50={s['p50_latency_s']}s")
    print("=" * 66)


def main(argv=None):
    ap = argparse.ArgumentParser(description="QuantumLabs eval harness")
    ap.add_argument("--tasks", default=_DEFAULT_TASKS)
    ap.add_argument("--label", default="run", help="rapor etiketi (baseline/cand/...)")
    ap.add_argument("--model", default=None, help="model id override")
    ap.add_argument("--limit", type=int, default=0, help="ilk N gorev (0=hepsi)")
    ap.add_argument("--baseline", default=None, help="kiyaslanacak baseline raporu (json)")
    args = ap.parse_args(argv)

    _load_dotenv(os.path.join(_REPO_ROOT, ".env"))   # pod env'ini gorunur yap
    cfg = _model_config(args.model)
    tasks = _load_tasks(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]

    print(f"[eval] {len(tasks)} gorev, model={cfg.model}")
    results = []
    for i, task in enumerate(tasks, 1):
        print(f"[eval] ({i}/{len(tasks)}) {task['id']} …", flush=True)
        results.append(run_task(task, cfg))

    report = {
        "label": args.label,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": cfg.model,
        "config": {"memory_injection": False, "profile_injection": False},
        "summary": _summarize(results),
        "results": results,
    }
    os.makedirs(_REPORTS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(_REPORTS_DIR, f"{stamp}_{args.label}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    _print_report(report)
    print(f"[eval] rapor -> {os.path.relpath(out, _REPO_ROOT)}")

    if args.baseline:
        from eval.compare import compare_reports
        with open(args.baseline, encoding="utf-8") as f:
            base = json.load(f)
        rc = compare_reports(base, report)
        sys.exit(rc)


if __name__ == "__main__":
    main()
