"""GET /sessions (+ /tasks alias) — session listesi (v0.5.3-pre)."""
import json

from fastapi.testclient import TestClient

import api.main as main
from api.main import app

client = TestClient(app)


def _write_session(tmp_path, session_id, events):
    tdir = tmp_path / ".quantumlabs" / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    with open(tdir / f"{session_id}.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    r = client.get("/sessions")
    assert r.status_code == 200
    assert r.json() == []                         # 404 DEGIL, bos liste
    assert client.get("/tasks").json() == []      # /tasks alias -> artik 405 degil


def test_populated_list(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    sid = "2026-07-03_101112_abcd1234"
    _write_session(tmp_path, sid, [
        {"type": "user", "content": "README dosyasini ozetle", "ts": "2026-07-03T10:11:12+00:00", "step": 0},
        {"type": "assistant", "content": "...", "ts": "2026-07-03T10:11:13+00:00", "step": 1},
    ])
    data = client.get("/sessions").json()
    assert len(data) == 1
    s = data[0]
    assert s["id"] == sid
    assert s["title"] == "README dosyasini ozetle"          # ilk user mesaji
    assert s["created_at"] == "2026-07-03T10:11:12+00:00"    # ilk event ts


def test_title_truncated_and_untitled(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    long_task = "x" * 100
    _write_session(tmp_path, "2026-07-03_101112_long", [
        {"type": "user", "content": long_task, "ts": "2026-07-03T10:11:12+00:00", "step": 0},
    ])
    # user event'i olmayan oturum -> "Untitled session", created_at sid'den turer
    _write_session(tmp_path, "2026-07-03_120000_noone", [
        {"type": "assistant", "content": "x", "ts": "2026-07-03T12:00:00+00:00", "step": 1},
    ])
    by_id = {s["id"]: s for s in client.get("/sessions").json()}
    assert len(by_id["2026-07-03_101112_long"]["title"]) == 60       # ~60 kirpma
    assert by_id["2026-07-03_120000_noone"]["title"] == "Untitled session"
    assert by_id["2026-07-03_120000_noone"]["created_at"] == "2026-07-03T12:00:00+00:00"
