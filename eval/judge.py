"""QuantumLabs — Eval judge (LLM-as-judge).

Bir gorevin rubric'i + agent'in cevabi -> {score 0..1, passed, reason}. Deterministik
degil (model tabanli) ama esik + rubric ile tutarli. Judge modeli AYRI secilebilir
(QL_JUDGE_* env) — ideali degerlendirilen modelden GUCLU bir judge; ayni pod da olur.

SINIRLAMA: judge de 4B pod ise "zayif judge" — skorlar gurultulu olabilir. Daha guclu
bir judge (buyuk model / API) QL_JUDGE_BASE_URL + QL_JUDGE_API_KEY + QL_JUDGE_MODEL ile
takilabilir. Best-effort: judge hata -> score 0, passed False, reason'da hata.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import ModelConfig, ask_model, default_config, quantum_pod_config

PASS_THRESHOLD = 0.7   # score >= bu -> passed

_JUDGE_SYSTEM = (
    "You are a strict, fair evaluator of an AI coding agent's answers. "
    "You are given the user's TASK, a RUBRIC describing what a good answer must do, "
    "and the agent's ANSWER. Score how well the ANSWER satisfies the RUBRIC.\n"
    "Return ONLY a JSON object, no other text:\n"
    '{\"score\": <float 0..1>, \"reason\": \"<one sentence>\"}\n'
    "0 = fails the rubric entirely, 1 = fully satisfies it. Be concrete and consistent. "
    "Judge ONLY against the rubric; do not reward verbosity."
)


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).replace("<think>", "").strip()


def _judge_config() -> ModelConfig:
    """Ayri judge endpoint'i (QL_JUDGE_*) set ise onu; degilse degerlendirmede
    kullanilan pod/default config'i kullan."""
    base = os.getenv("QL_JUDGE_BASE_URL")
    key = os.getenv("QL_JUDGE_API_KEY")
    model = os.getenv("QL_JUDGE_MODEL")
    if base and model:
        return ModelConfig(base_url=base, api_key=key or "x", model=model, temperature=0.0)
    if os.getenv("QUANTUM_POD_BASE_URL") and os.getenv("QUANTUM_POD_API_KEY"):
        return quantum_pod_config()
    return default_config()


def score(task: dict, answer: Optional[str], cfg: Optional[ModelConfig] = None) -> dict:
    """Rubric'e gore cevabi puanla. Donus: {score, passed, reason}."""
    if not answer or not str(answer).strip():
        return {"score": 0.0, "passed": False, "reason": "bos/None cevap"}
    cfg = cfg or _judge_config()
    user = (
        f"TASK:\n{task.get('prompt','')}\n\n"
        f"RUBRIC:\n{task.get('rubric','')}\n\n"
        f"ANSWER:\n{_strip_think(str(answer))}\n\n"
        "Return the JSON now."
    )
    try:
        raw = ask_model(
            [{"role": "system", "content": _JUDGE_SYSTEM},
             {"role": "user", "content": user}],
            cfg,
        )
        clean = _strip_think(raw)
        s, e = clean.find("{"), clean.rfind("}")
        obj = json.loads(clean[s:e + 1]) if s != -1 and e > s else {}
        val = float(obj.get("score", 0.0))
        val = max(0.0, min(1.0, val))
        return {"score": round(val, 2), "passed": val >= PASS_THRESHOLD,
                "reason": str(obj.get("reason", ""))[:200]}
    except Exception as ex:  # noqa: BLE001 — judge hatasi eval'i dusurmez
        return {"score": 0.0, "passed": False, "reason": f"judge hata: {ex}"}
