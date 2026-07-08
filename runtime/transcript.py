"""QuantumLabs — Transcript persistence (v0.4.0 B2): her agent turu jsonl'e.

SADECE yazma katmani; embedding / index / retrieval B3'te. Best-effort:
persistence hatasi agent'i ASLA dusurmez (exception yutulur, stderr'e tek satir
uyari) — bir dosya yazilamadi diye tur cokmesin.

Yol: <workspace>/.quantumlabs/transcripts/<session_id>.jsonl
Her satir bir event (json). Otomatik alanlar: ts (ISO/UTC), step, session_id.

Event tipleri (type):
    "user"        -> gorev/prompt
    "assistant"   -> model yaniti/action (ham metin)
    "observation" -> tool sonucu (tool + ok + content); content ILK 2000 karakter,
                     kirpildiysa truncated=True (dev dosya icerikleri jsonl'i sismesin)
"""
from __future__ import annotations

import datetime
import json
import os
import sys

_TRANSCRIPT_SUBDIR = os.path.join(".quantumlabs", "transcripts")
_MAX_OBS_CONTENT = 2000


def append_event(session, event: dict) -> None:
    """event'i session transcript'ine ekler. Best-effort (hata sizmaz).

    open("a") her cagrida: surec cokse bile o ana kadar yazilanlar diskte durur.
    """
    try:
        enriched = dict(event)

        # observation content'ini kirp (buyuk dosya okumalari transcript'i sismesin).
        if enriched.get("type") == "observation":
            content = enriched.get("content")
            if isinstance(content, str) and len(content) > _MAX_OBS_CONTENT:
                enriched["content"] = content[:_MAX_OBS_CONTENT]
                enriched["truncated"] = True

        # Otomatik/otoriter alanlar (caller verse de bunlar yazar).
        enriched["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        enriched["step"] = getattr(session, "step", None)
        enriched["session_id"] = session.session_id

        directory = os.path.join(session.workspace, _TRANSCRIPT_SUBDIR)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{session.session_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — best-effort; agent'i asla dusurme
        print(f"[transcript] yazma hatasi (yok sayildi): {e}", file=sys.stderr)


def rebuild_history(path: str) -> list:
    """Bir transcript jsonl'i run_agent'in bekledigi mesaj tape'ine cevirir.

    user->'Gorev: ...', assistant->ham metin, observation->'Aracin sonucu: ...'
    (run_agent'in ic mesaj formatiyla birebir). Bozuk satir atlanir; dosya yoksa [].

    TEK KAYNAK: hem API follow-up (api/main.py) hem eval harness (eval/harness.py)
    bunu kullanir -> eval, prod'un kullandigi AYNI history kurulumunu test eder."""
    msgs: list = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = ev.get("type")
                content = ev.get("content")
                if content is None:
                    continue
                if typ == "user":
                    msgs.append({"role": "user", "content": f"Gorev: {content}"})
                elif typ == "assistant":
                    msgs.append({"role": "assistant", "content": content})
                elif typ == "observation":
                    msgs.append({"role": "user", "content": f"Aracin sonucu:\n{content}"})
    except OSError:
        pass
    return msgs
