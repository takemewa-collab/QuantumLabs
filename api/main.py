"""QuantumLabs API (v0.5.0 S1b): FastAPI cekirdegi.

3 endpoint, localhost, auth YOK, tek worker. Onay akisi YOK -> guvenlik default
DENY (DenyAllApprover). Her istek kendi Session'ini alir (S1a izolasyonu).

TASK KAYDI IN-MEMORY (TASKS dict): surec yeniden baslayinca kaybolur. Kalicilik
S5 isi. Tek-worker varsayimi (uvicorn --workers 1) — coklu worker'da dict
paylasilmaz.

Onay akisi (v0.5.1-a): default approver artik WebApprover. Yazma/komut onay
gerektirdiginde task "waiting_approval"a gecer, SSE'de `approval_needed` sinyali
cikar; POST /approvals/{id}/decision ile karar verilir. Karar gelmezse timeout ->
DENY (WebApprover). run_command ARTIK API'de kullanilabilir (inline input soktuldu).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.code_agent import run_agent
from api.approvers import WebApprover, get_pending, list_pending, resolve_approval
from runtime.session import Session
from runtime.transcript import _TRANSCRIPT_SUBDIR  # yol deseni icin tek kaynak

APPROVAL_TIMEOUT_SEC = 300   # web onayi bu surede gelmezse -> DENY (asili task yok)

DEFAULT_WORKSPACE = os.path.abspath(os.getcwd())

# In-memory task kaydi (tek worker; kalicilik yok — S5).
TASKS: dict = {}

app = FastAPI(title="QuantumLabs API")

# Web frontend (Next.js, localhost:3000) tarayicidan cagirabilsin diye CORS.
# localhost-only + auth yok (S1b kapsam); prod'da origin listesi daraltilir.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    task: str
    workspace: Optional[str] = None
    max_steps: int = 12


def _transcript_path(workspace: str, session_id: str) -> str:
    return os.path.join(workspace, _TRANSCRIPT_SUBDIR, f"{session_id}.jsonl")


def _run_task(task_id: str, task: str, session, workspace: str, max_steps: int) -> None:
    """Arka planda run_agent'i kosar, TASKS kaydini done/failed'e cevirir."""
    try:
        approver = WebApprover(task_id, TASKS, timeout_sec=APPROVAL_TIMEOUT_SEC)
        result = run_agent(task, session=session, workspace=workspace,
                           approver=approver, max_steps=max_steps)
        TASKS[task_id]["status"] = "done"
        TASKS[task_id]["result"] = result
    except Exception as e:  # noqa: BLE001 — hata task kaydina yazilir, servisi dusurmez
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["error"] = str(e)


@app.post("/tasks")
def create_task(req: TaskRequest, background: BackgroundTasks):
    task_id = uuid.uuid4().hex[:8]
    workspace = req.workspace or DEFAULT_WORKSPACE
    session = Session(workspace)
    # session_id zaman-damgasi saniye cozunurluklu; ayni saniyedeki iki gorev
    # CAKISMASIN diye benzersiz task_id ekle (transcript dosyasi da benzersiz olur).
    session.session_id = f"{session.session_id}_{task_id}"
    TASKS[task_id] = {
        "id": task_id, "status": "running", "workspace": workspace,
        "session_id": session.session_id, "result": None, "error": None,
        "pending_approval": None,
    }
    background.add_task(_run_task, task_id, req.task, session, workspace, req.max_steps)
    return {"task_id": task_id, "session_id": session.session_id,
            "transcript_path": _transcript_path(workspace, session.session_id)}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="task bulunamadi")
    return TASKS[task_id]


@app.get("/tasks/{task_id}/stream")
def stream_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="task bulunamadi")
    rec = TASKS[task_id]
    path = _transcript_path(rec["workspace"], rec["session_id"])

    def event_gen():
        pos = 0
        waited = 0
        sent_approval = None   # ayni approval_id icin BIR KEZ approval_needed yolla
        # transcript dosyasi henuz yoksa kisa bekle-yeniden-dene (~15s tavan).
        while not os.path.exists(path) and rec["status"] not in ("done", "failed") and waited < 50:
            time.sleep(0.3)
            waited += 1
        while True:
            # waiting_approval da "bitmemis" sayilir; sadece done/failed kapatir.
            finished = rec["status"] in ("done", "failed")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    if line.strip():
                        yield f"data: {line}\n\n"
            # Onay bekleniyorsa UI'ya BIR KEZ sinyal (tekrar etme).
            pend = rec.get("pending_approval")
            if rec["status"] == "waiting_approval" and pend and pend["approval_id"] != sent_approval:
                sent_approval = pend["approval_id"]
                yield f"event: approval_needed\ndata: {json.dumps(pend, ensure_ascii=False)}\n\n"
            if finished:                            # son satirlari attik, kapat
                end = {"status": rec["status"], "result": rec["result"], "error": rec["error"]}
                yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
                break
            time.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# Onay endpoint'leri (v0.5.1-a)
# --------------------------------------------------------------------------- #
class DecisionBody(BaseModel):
    approved: bool
    reason: Optional[str] = ""


@app.get("/approvals")
def approvals():
    return {"pending": list_pending()}


@app.get("/approvals/{approval_id}")
def approval(approval_id: str):
    p = get_pending(approval_id)
    if p is None:
        raise HTTPException(status_code=404, detail="approval bulunamadi")
    return p


@app.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, body: DecisionBody):
    status = resolve_approval(approval_id, body.approved, body.reason or "")
    if status == "not_found":
        raise HTTPException(status_code=404, detail="approval bulunamadi")
    if status == "already":
        raise HTTPException(status_code=409, detail="karar zaten verilmis")
    return {"status": "ok", "approval_id": approval_id, "approved": body.approved}
