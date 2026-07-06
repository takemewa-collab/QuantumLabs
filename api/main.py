"""QuantumLabs API (v0.5.0 S1b): FastAPI cekirdegi.

3 endpoint, localhost, auth YOK, tek worker. Onay akisi YOK -> guvenlik default
DENY (DenyAllApprover). Her istek kendi Session'ini alir (S1a izolasyonu).

TASK KAYDI IN-MEMORY (TASKS dict): surec yeniden baslayinca kaybolur. Ama
transcript'ler diskte kalici; S5'te surec-oncesi/tamamlanmis session'lar
diskten SALT-OKUNUR replay ile acilir (stream_task -> _replay_gen). Durable
"index" = transcript dizini; baslangicta bellege tam yukleme YOK.
Tek-worker varsayimi (uvicorn --workers 1) — coklu worker'da dict paylasilmaz.

Onay akisi (v0.5.1-a): default approver artik WebApprover. Yazma/komut onay
gerektirdiginde task "waiting_approval"a gecer, SSE'de `approval_needed` sinyali
cikar; POST /approvals/{id}/decision ile karar verilir. Karar gelmezse timeout ->
DENY (WebApprover). run_command ARTIK API'de kullanilabilir (inline input soktuldu).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from dataclasses import replace
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.code_agent import run_agent
from agents.llm import quantum_pod_config
from api.approvers import WebApprover, get_pending, list_pending, resolve_approval
from runtime.session import Session
from runtime.transcript import _TRANSCRIPT_SUBDIR  # yol deseni icin tek kaynak


def _load_dotenv(path: str) -> None:
    """Minimal .env yukleyici (dep yok): KEY=VALUE satirlarini os.environ'a koyar.
    Zaten set olan degiskeni EZMEZ; # yorumlarini ve bos satirlari atlar."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass  # .env yoksa sessizce gec — env dogrudan process'ten okunur


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

APPROVAL_TIMEOUT_SEC = 300   # web onayi bu surede gelmezse -> DENY (asili task yok)

DEFAULT_WORKSPACE = os.path.abspath(os.getcwd())

# In-memory task kaydi (tek worker; kalicilik yok — S5).
TASKS: dict = {}


def require_auth(
    authorization: Optional[str] = Header(default=None),
    key: Optional[str] = None,
) -> None:
    """Opsiyonel API anahtari. API_KEY env SET ise TUM route'larda (SSE dahil)
    dogru token zorunlu; UNSET ise auth kapali (bugunku davranis, geriye uyum).

    EventSource custom header gonderemedigi icin SSE'de Authorization: Bearer
    YANINDA ?key=<token> query param'i da kabul edilir."""
    expected = os.getenv("API_KEY")
    if not expected:
        return
    supplied = None
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization[len("Bearer "):].strip()
    elif key:
        supplied = key
    if supplied != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


app = FastAPI(title="QuantumLabs API", dependencies=[Depends(require_auth)])


def _allowed_origins() -> list:
    """CORS origin listesi ALLOWED_ORIGINS env'inden (virgul-ayrik).

    Dev default: http://localhost:3000. Prod ornek:
        ALLOWED_ORIGINS="https://q-labs.dev,https://www.q-labs.dev"
    """
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


# CORS: izin verilen origin'ler env'den (baslangicta okunur).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
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
    # Tek dallanma: QUANTUM_POD_BASE_URL set ise Session'i uzak OpenAI-uyumlu
    # pod'a (model="quantum") yonlendir; set degilse lokal davranis birebir korunur.
    if os.getenv("QUANTUM_POD_BASE_URL"):
        session = Session(workspace,
                          model_config=replace(quantum_pod_config(), model="quantum"))
    else:
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


# --------------------------------------------------------------------------- #
# Session listesi (v0.5.3-pre) — sidebar 405 fix.
#
# Kaynak: DEFAULT_WORKSPACE/.quantumlabs/transcripts/*.jsonl (v0.4.0 persistence).
# Her jsonl = bir oturum. id = dosya adi (session_id). Ayni handler HEM /sessions
# HEM /tasks'ta: frontend (v0.5.1-b route uyumu) GET /tasks cagiriyor; /sessions
# de gorevde istenen isim. Oturum yoksa 404 DEGIL, bos liste.
# --------------------------------------------------------------------------- #
def _created_from_sid(session_id: str) -> str:
    """session_id 'YYYY-MM-DD_HHMMSS[_...]' -> iso8601. Cozulemezse "" doner."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})", session_id)
    if not m:
        return ""
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def _session_meta(path: str, session_id: str):
    """(created_at, title): ilk event ts'i + ilk user mesajinin ilk ~60 karakteri."""
    created_at = None
    title = None
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
                if created_at is None and ev.get("ts"):
                    created_at = ev["ts"]
                if title is None and ev.get("type") == "user":
                    content = (ev.get("content") or "").strip()
                    if content:
                        title = content[:60]
                if created_at and title:
                    break
    except OSError:
        pass
    return (created_at or _created_from_sid(session_id)), (title or "Untitled session")


def _list_sessions() -> list:
    tdir = os.path.join(DEFAULT_WORKSPACE, _TRANSCRIPT_SUBDIR)
    if not os.path.isdir(tdir):
        return []
    sessions = []
    for name in sorted(os.listdir(tdir), reverse=True):   # en yeni ustte (isim=zaman damgasi)
        if not name.endswith(".jsonl"):
            continue
        session_id = name[: -len(".jsonl")]
        created_at, title = _session_meta(os.path.join(tdir, name), session_id)
        sessions.append({"id": session_id, "created_at": created_at, "title": title})
    return sessions


@app.get("/sessions")
@app.get("/tasks")
def list_sessions():
    return _list_sessions()


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="task bulunamadi")
    return TASKS[task_id]


def _live_gen(rec: dict, path: str):
    """CANLI session: transcript'i tail eder, approval sinyali + end yollar."""
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
        pend = rec.get("pending_approval")
        if rec["status"] == "waiting_approval" and pend and pend["approval_id"] != sent_approval:
            sent_approval = pend["approval_id"]
            yield f"event: approval_needed\ndata: {json.dumps(pend, ensure_ascii=False)}\n\n"
        if finished:                            # son satirlari attik, kapat
            end = {"status": rec["status"], "result": rec["result"], "error": rec["error"]}
            yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
            break
        time.sleep(0.3)


def _replay_gen(path: str):
    """S5: surec-oncesi / tamamlanmis session -> DISKTEN salt-okunur replay.

    Satir satir okur (tum sessionlar bellege YUKLENMEZ), bozuk/yarim jsonl
    satirlarini atlar, sonra event:end yollar. RESUME/tail YOK — tamamlanmis
    session tekrar canli akmaz; sadece transcript'i gosterir."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)          # gecerli JSON mi?
                except json.JSONDecodeError:
                    continue                  # bozuk/yarim satir -> atla
                yield f"data: {line}\n\n"
    except OSError:
        pass
    end = {"status": "done", "result": None, "error": None, "replayed": True}
    yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"


@app.get("/tasks/{ident}/stream")
def stream_task(ident: str):
    # ident = CANLI task_id (kisa) VEYA session_id (transcript dosya adi, kalici).
    rec = TASKS.get(ident)
    if rec is None:
        # live bir session'in session_id'siyle mi cagrildi?
        rec = next((r for r in TASKS.values() if r.get("session_id") == ident), None)

    if rec is not None:                        # CANLI -> tail
        path = _transcript_path(rec["workspace"], rec["session_id"])
        return StreamingResponse(_live_gen(rec, path), media_type="text/event-stream")

    # GECMIS (surec-oncesi / tamamlanmis): diskten salt-okunur replay.
    hist_path = _transcript_path(DEFAULT_WORKSPACE, ident)
    if os.path.exists(hist_path):
        return StreamingResponse(_replay_gen(hist_path), media_type="text/event-stream")

    raise HTTPException(status_code=404, detail="session bulunamadi")


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
