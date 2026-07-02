"""WebApprover + CommandProposal + run_command ctx.approver (v0.5.1-a)."""
import json
import os
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

import agents.code_agent as ca
from api.approvers import PENDING, RESOLVED, WebApprover, list_pending, resolve_approval
from api.main import app
from protocols.safety import ApprovalResult, CommandProposal
from tools import registry

client = TestClient(app)


class _FlagApprover:
    """request cagrilirsa isaretler (kind kaydeder). Blacklist testinde 'cagrilmadi' kaniti."""
    def __init__(self):
        self.called_with = None

    def request(self, proposal):
        self.called_with = getattr(proposal, "kind", "?")
        return ApprovalResult.approve()


# --- 1) CommandProposal kind dallanmasi + blacklist onaya dusmez ---
def test_run_command_uses_command_proposal(tmp_path):
    ap = _FlagApprover()
    ctx = SimpleNamespace(cwd=str(tmp_path), approver=ap)
    obs = registry.dispatch("run_command", {"command": "echo hi"}, ctx)
    assert obs.ok is True and "hi" in obs.content
    assert ap.called_with == "command"          # CommandProposal ile soruldu


def test_blocked_command_not_asked(tmp_path):
    ap = _FlagApprover()
    ctx = SimpleNamespace(cwd=str(tmp_path), approver=ap)
    obs = registry.dispatch("run_command", {"command": "rm -rf /"}, ctx)
    assert "engellendi" in obs.content
    assert ap.called_with is None               # approver HIC cagrilmadi
    assert list_pending() == []                 # PENDING'e dusmedi


# --- 2) WebApprover approve / reject (ayri thread) ---
def _webapprover_in_thread(timeout_sec=5):
    tasks = {"t1": {"status": "running", "pending_approval": None}}
    approver = WebApprover("t1", tasks, timeout_sec=timeout_sec)
    result_box = {}

    def worker():
        result_box["res"] = approver.request(CommandProposal(command="ls", cwd="/tmp"))

    th = threading.Thread(target=worker)
    th.start()
    # PENDING dolana kadar bekle
    for _ in range(200):
        if list_pending():
            break
        time.sleep(0.01)
    return th, tasks, result_box


def test_webapprover_approve():
    th, tasks, box = _webapprover_in_thread()
    pend = list_pending()
    assert len(pend) == 1 and tasks["t1"]["status"] == "waiting_approval"
    assert resolve_approval(pend[0]["approval_id"], True, "ok") == "ok"
    th.join(timeout=5)
    assert box["res"].approved is True
    assert box["res"].approver == "web"
    assert tasks["t1"]["status"] == "running" and tasks["t1"]["pending_approval"] is None
    assert list_pending() == []


def test_webapprover_reject():
    th, tasks, box = _webapprover_in_thread()
    pend = list_pending()
    resolve_approval(pend[0]["approval_id"], False, "olmaz")
    th.join(timeout=5)
    assert box["res"].approved is False
    assert box["res"].reason == "olmaz"


def test_webapprover_timeout():
    tasks = {"t2": {"status": "running", "pending_approval": None}}
    approver = WebApprover("t2", tasks, timeout_sec=0.4)
    t0 = time.time()
    res = approver.request(CommandProposal(command="ls", cwd="/tmp"))   # karar gelmez
    assert 0.3 < time.time() - t0 < 3.0
    assert res.approved is False and "zaman" in res.reason      # TIMEOUT -> DENY
    assert list_pending() == []                                 # thread serbest, temizlendi


def test_resolve_404_and_409():
    assert resolve_approval("yokboyle", True) == "not_found"
    th, tasks, box = _webapprover_in_thread()
    aid = list_pending()[0]["approval_id"]
    assert resolve_approval(aid, True) == "ok"
    th.join(timeout=5)
    assert resolve_approval(aid, True) == "already"             # zaten kararli


# --- 3) API tam dongu (LLM'siz): write -> approval_needed -> approve -> done ---
def _fake_write_then_final():
    calls = {"n": 0}

    def fake(messages, cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"tool":"write_file","args":{"path":"yeni.txt","content":"veri"}}'
        return '{"tool":"final","args":{"answer":"bitti"}}'
    return fake


def _drive_decision(approve, workspace, seen):
    """PENDING'de bu workspace'e ait onay cikinca karar ver."""
    for _ in range(400):
        for p in list_pending():
            if p["approval_id"] not in seen:
                seen.add(p["approval_id"])
                resolve_approval(p["approval_id"], approve, "auto-test")
                return
        time.sleep(0.02)


def test_api_write_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "ask_model", _fake_write_then_final())
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    seen = set()
    driver = threading.Thread(target=_drive_decision, args=(True, str(tmp_path), seen))
    driver.start()
    body = client.post("/tasks", json={"task": "yaz", "workspace": str(tmp_path)}).json()
    driver.join(timeout=10)

    rec = client.get(f"/tasks/{body['task_id']}").json()
    assert rec["status"] == "done" and rec["result"] == "bitti"
    assert (tmp_path / "yeni.txt").read_text(encoding="utf-8") == "veri"   # onay -> yazildi


def test_api_write_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "ask_model", _fake_write_then_final())
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    seen = set()
    driver = threading.Thread(target=_drive_decision, args=(False, str(tmp_path), seen))
    driver.start()
    body = client.post("/tasks", json={"task": "yaz", "workspace": str(tmp_path)}).json()
    driver.join(timeout=10)

    rec = client.get(f"/tasks/{body['task_id']}").json()
    assert rec["status"] == "done"
    assert not (tmp_path / "yeni.txt").exists()                # red -> yazilMAdi


# --- 4) SSE approval_needed sinyali (dogrudan TASKS kurgusu, deadlock'suz) ---
def test_sse_emits_approval_needed(tmp_path):
    from api.main import TASKS
    tid = "ssetest"
    sid = "2026-07-02_sse"
    tdir = tmp_path / ".quantumlabs" / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "content": "x"}) + "\n", encoding="utf-8")
    TASKS[tid] = {"id": tid, "status": "waiting_approval", "workspace": str(tmp_path),
                  "session_id": sid, "result": None, "error": None,
                  "pending_approval": {"approval_id": "a1", "kind": "command",
                                       "payload": {"command": "ls", "cwd": "/tmp"}}}

    def flip_done():
        time.sleep(0.6)
        TASKS[tid]["status"] = "done"

    threading.Thread(target=flip_done).start()
    with client.stream("GET", f"/tasks/{tid}/stream") as resp:
        text = "".join(resp.iter_text())
    del TASKS[tid]
    assert "event: approval_needed" in text
    assert "event: end" in text
