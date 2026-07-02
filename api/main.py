"""QuantumLabs API (v0.5.0 S1b): FastAPI cekirdegi.

3 endpoint, localhost, auth YOK, tek worker. Onay akisi YOK -> guvenlik default
DENY (DenyAllApprover). Her istek kendi Session'ini alir (S1a izolasyonu).

TASK KAYDI IN-MEMORY (TASKS dict): surec yeniden baslayinca kaybolur. Kalicilik
S5 isi. Tek-worker varsayimi (uvicorn --workers 1) — coklu worker'da dict
paylasilmaz.

run_command UYARISI: shell.py run_command onayi hala inline input(). Arka plan
thread'inde stdin yok -> EOFError -> tool ok=False doner (deadlock DEGIL, ama
komut calismaz). Yani run_command S2'ye (web onay akisi) kadar API'de pratikte
kullanilamaz.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.code_agent import run_agent
from api.approvers import DenyAllApprover
from runtime.session import Session
from runtime.transcript import _TRANSCRIPT_SUBDIR  # yol deseni icin tek kaynak

DEFAULT_WORKSPACE = os.path.abspath(os.getcwd())

# In-memory task kaydi (tek worker; kalicilik yok — S5).
TASKS: dict = {}

app = FastAPI(title="QuantumLabs API")


class TaskRequest(BaseModel):
    task: str
    workspace: Optional[str] = None
    max_steps: int = 12


def _transcript_path(workspace: str, session_id: str) -> str:
    return os.path.join(workspace, _TRANSCRIPT_SUBDIR, f"{session_id}.jsonl")


def _run_task(task_id: str, task: str, session, workspace: str, max_steps: int) -> None:
    """Arka planda run_agent'i kosar, TASKS kaydini done/failed'e cevirir."""
    try:
        result = run_agent(task, session=session, workspace=workspace,
                           approver=DenyAllApprover(), max_steps=max_steps)
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
        # transcript dosyasi henuz yoksa kisa bekle-yeniden-dene (~15s tavan).
        while not os.path.exists(path) and rec["status"] == "running" and waited < 50:
            time.sleep(0.3)
            waited += 1
        while True:
            running = rec["status"] == "running"   # okumadan ONCE yakala
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    if line.strip():
                        yield f"data: {line}\n\n"
            if not running:                         # done/failed -> son satirlari attik, kapat
                end = {"status": rec["status"], "result": rec["result"], "error": rec["error"]}
                yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
                break
            time.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
