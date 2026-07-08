"""QuantumLabs — Veri kuratorlugu: transcript + feedback -> SFT egitim seti.

Self-improvement cark'inin YAKITI. Kalici transcript'leri (.quantumlabs/transcripts)
ve 👍/👎 geri bildirimini (.quantumlabs/feedback.jsonl) okuyup fine-tune icin
kaliteli ornekler cikarir. SFT formatinda ({messages:[...]}) yazar — tam ReAct
tape'i (system + gorev + action/observation + final) modele "iyi yorunge" ogretir.

KALITE FILTRESI (muhafazakar — kotu ornek egitime SIZMASIN):
  KEEP  : feedback 👍  VEYA  (final'e ulasti  VE  👎 degil  VE  tool-hatasi az)
  DROP  : feedback 👎  VEYA  final yok (max-step/hata)  VEYA  cok tool-hatasi

Cikti: train/data/sft.jsonl  (+ ozet). DPO (chosen/rejected) ileride — yeterli
esli 👍/👎 verisi birikince (simdilik SFT-only). Insan-onayli: bu SET fine-tune'a
girmeden once GOZDEN GECIRILIR (kucuk, denetlenebilir).

Kullanim:
    python -m train.curate                 # DEFAULT_WORKSPACE'ten uret
    python -m train.curate --min-signal thumbs_up   # sadece 👍 olanlar
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_TRANSCRIPTS = os.path.join(".quantumlabs", "transcripts")
_FEEDBACK = os.path.join(".quantumlabs", "feedback.jsonl")
_OUT_DIR = os.path.join(_REPO_ROOT, "train", "data")

_MAX_TOOL_ERRORS = 1   # bundan fazla tool-hatasi olan yorunge "iyi ornek" sayilmaz


def _load_feedback(workspace):
    """session_id -> son rating ('up'/'down'). Sonuncu karar gecerli."""
    path = os.path.join(workspace, _FEEDBACK)
    latest = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = r.get("session_id")
                if sid and r.get("rating") in ("up", "down"):
                    latest[sid] = r["rating"]
    except OSError:
        pass
    return latest


def _events(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _is_final(content):
    """assistant content'i 'final' action'i mi (JSON tool=='final')."""
    s, e = content.find("{"), content.rfind("}")
    if s == -1 or e <= s:
        return False
    try:
        obj = json.loads(content[s:e + 1])
    except (ValueError, TypeError):
        return False
    return isinstance(obj, dict) and obj.get("tool") == "final"


def _to_messages(events):
    """Transcript event'lerini SFT chat tape'ine cevir (ReAct yorungesi)."""
    msgs = []
    for ev in events:
        t, c = ev.get("type"), ev.get("content")
        if c is None:
            continue
        if t == "user":
            msgs.append({"role": "user", "content": f"Gorev: {c}"})
        elif t == "assistant":
            msgs.append({"role": "assistant", "content": c})
        elif t == "observation":
            msgs.append({"role": "user", "content": f"Aracin sonucu:\n{c}"})
    return msgs


def curate(workspace, min_signal="final"):
    """Transcript'leri kaliteye gore filtrele -> SFT ornekleri + ozet."""
    feedback = _load_feedback(workspace)
    tdir = os.path.join(workspace, _TRANSCRIPTS)
    kept, stats = [], {"total": 0, "kept": 0, "drop_down": 0, "drop_nofinal": 0,
                       "drop_toolerr": 0, "thumbs_up": 0}
    if not os.path.isdir(tdir):
        return kept, stats
    for name in sorted(os.listdir(tdir)):
        if not name.endswith(".jsonl"):
            continue
        sid = name[: -len(".jsonl")]
        stats["total"] += 1
        events = _events(os.path.join(tdir, name))
        rating = feedback.get(sid)
        final_reached = any(e.get("type") == "assistant" and _is_final(e.get("content", ""))
                            for e in events)
        tool_errors = sum(1 for e in events if e.get("type") == "observation"
                          and e.get("ok") is False)

        # KARAR
        if rating == "down":
            stats["drop_down"] += 1
            continue
        signal = "thumbs_up" if rating == "up" else ("final" if final_reached else None)
        if min_signal == "thumbs_up" and signal != "thumbs_up":
            continue
        if signal is None:
            stats["drop_nofinal"] += 1
            continue
        if signal != "thumbs_up" and tool_errors > _MAX_TOOL_ERRORS:
            stats["drop_toolerr"] += 1
            continue

        msgs = _to_messages(events)
        if len(msgs) < 2:      # en az gorev + bir cevap
            stats["drop_nofinal"] += 1
            continue
        kept.append({"session_id": sid, "signal": signal, "messages": msgs})
        stats["kept"] += 1
        if signal == "thumbs_up":
            stats["thumbs_up"] += 1
    return kept, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="QuantumLabs SFT veri kuratorlugu")
    ap.add_argument("--workspace", default=_REPO_ROOT)
    ap.add_argument("--min-signal", choices=["final", "thumbs_up"], default="final",
                    help="'final': final'e ulasan + 👎 olmayan; 'thumbs_up': sadece 👍")
    ap.add_argument("--out", default=os.path.join(_OUT_DIR, "sft.jsonl"))
    args = ap.parse_args(argv)

    kept, stats = curate(args.workspace, args.min_signal)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for ex in kept:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print("=" * 56)
    print("VERI KURATORLUGU (SFT)")
    print("=" * 56)
    print(f"  transcript      : {stats['total']}")
    print(f"  KEEP (ornek)    : {stats['kept']}  (👍: {stats['thumbs_up']})")
    print(f"  drop 👎         : {stats['drop_down']}")
    print(f"  drop final-yok  : {stats['drop_nofinal']}")
    print(f"  drop tool-hata  : {stats['drop_toolerr']}")
    print(f"  -> {os.path.relpath(args.out, _REPO_ROOT)}")
    print("=" * 56)
    if stats["kept"] < 20:
        print("NOT: ornek sayisi dusuk — anlamli fine-tune icin daha cok gercek "
              "kullanim + 👍/👎 birikmeli. Pipeline hazir; veri biriktikce buyur.")


if __name__ == "__main__":
    main()
