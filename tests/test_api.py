"""api/main.py — FastAPI cekirdegi (v0.5.0 S1b). LLM'siz (ask_model monkeypatch)."""
import json
import os

import pytest
from fastapi.testclient import TestClient

import agents.code_agent as ca
from api.main import app

client = TestClient(app)

FINAL = '{"thought":"bitti","tool":"final","args":{"answer":"api cevap"}}'


@pytest.fixture(autouse=True)
def _no_llm_no_ingest(monkeypatch):
    monkeypatch.setattr(ca, "ask_model", lambda m, c: FINAL)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)   # finally no-op


def _obs_events(workspace, session_id):
    path = os.path.join(workspace, ".quantumlabs", "transcripts", f"{session_id}.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def test_post_then_get_done(tmp_path):
    r = client.post("/tasks", json={"task": "selam", "workspace": str(tmp_path)})
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] and body["session_id"] and body["transcript_path"]

    # TestClient BackgroundTasks'i post donmeden calistirir -> hemen done olmali
    g = client.get(f"/tasks/{body['task_id']}")
    assert g.status_code == 200
    rec = g.json()
    assert rec["status"] == "done"
    assert rec["result"] == "api cevap"


def test_two_tasks_isolated(tmp_path):
    ws1, ws2 = str(tmp_path / "a"), str(tmp_path / "b")
    os.makedirs(ws1); os.makedirs(ws2)
    b1 = client.post("/tasks", json={"task": "A", "workspace": ws1}).json()
    b2 = client.post("/tasks", json={"task": "B", "workspace": ws2}).json()

    assert b1["session_id"] != b2["session_id"]           # S1a izolasyonu API'den
    ev1 = _obs_events(ws1, b1["session_id"])
    ev2 = _obs_events(ws2, b2["session_id"])
    assert ev1[0]["type"] == "user" and ev1[0]["content"] == "A"
    assert ev2[0]["type"] == "user" and ev2[0]["content"] == "B"


def test_get_unknown_404():
    assert client.get("/tasks/yokboyle").status_code == 404


def test_stream_ends(tmp_path):
    body = client.post("/tasks", json={"task": "selam", "workspace": str(tmp_path)}).json()
    with client.stream("GET", f"/tasks/{body['task_id']}/stream") as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert "data:" in text                # en az bir event satiri
    assert "event: end" in text           # kapanis event'i
