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

import datetime
import json
import os
import re
import sys
import time
import uuid
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
    # Tek dallanma: QUANTUM_POD_BASE_URL VE QUANTUM_POD_API_KEY set ise Session'i
    # uzak OpenAI-uyumlu pod'a yonlendir (model/api_key/base_url quantum_pod_config'ten,
    # api_key OpenAI client'ta Bearer header olur). Ikisinden biri yoksa lokal davranis
    # birebir korunur.
    if os.getenv("QUANTUM_POD_BASE_URL") and os.getenv("QUANTUM_POD_API_KEY"):
        session = Session(workspace, model_config=quantum_pod_config())
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
# Follow-up (v0.6.0): var olan session'a AYNI transcript'e devam mesaji.
#
# Backend tek-atis degil artik: POST /tasks/{session_id}/messages yeni bir task
# KAYDI acar ama session_id'yi KORUR -> append_event ayni .jsonl'e yazar, stream
# ayni dosyayi tail eder. run_agent'a transcript'ten yeniden kurulan `history`
# gecilir; agent onceki turlari hatirlar. Cok-turlu chat bu sekilde.
# --------------------------------------------------------------------------- #
def _rebuild_history(path: str) -> list:
    """Transcript jsonl'i run_agent'in bekledigi mesaj tape'ine cevirir.

    user->'Gorev: ...', assistant->ham metin, observation->'Aracin sonucu: ...'
    (run_agent'in ic formatiyla birebir). Bozuk satir atlanir. Dosya yoksa []."""
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


class FollowupRequest(BaseModel):
    task: str
    workspace: Optional[str] = None
    max_steps: int = 12


@app.post("/tasks/{session_id}/messages")
def followup(session_id: str, req: FollowupRequest, background: BackgroundTasks):
    """Var olan session'a devam mesaji. session_id transcript'i yoksa 404."""
    workspace = req.workspace or DEFAULT_WORKSPACE
    path = _transcript_path(workspace, session_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="session bulunamadi")

    task_id = uuid.uuid4().hex[:8]
    if os.getenv("QUANTUM_POD_BASE_URL") and os.getenv("QUANTUM_POD_API_KEY"):
        session = Session(workspace, model_config=quantum_pod_config())
    else:
        session = Session(workspace)
    # session_id'yi EZ: append_event ayni dosyaya yazsin (yeni tur ayni transcript).
    session.session_id = session_id
    history = _rebuild_history(path)
    TASKS[task_id] = {
        "id": task_id, "status": "running", "workspace": workspace,
        "session_id": session_id, "result": None, "error": None,
        "pending_approval": None,
    }
    background.add_task(_run_followup, task_id, req.task, session, workspace,
                        req.max_steps, history)
    return {"task_id": task_id, "session_id": session_id,
            "transcript_path": path}


def _run_followup(task_id, task, session, workspace, max_steps, history):
    """_run_task ile ayni; sadece run_agent'a history gecer (onceki turlar)."""
    try:
        approver = WebApprover(task_id, TASKS, timeout_sec=APPROVAL_TIMEOUT_SEC)
        result = run_agent(task, session=session, workspace=workspace,
                           approver=approver, max_steps=max_steps, history=history)
        TASKS[task_id]["status"] = "done"
        TASKS[task_id]["result"] = result
    except Exception as e:  # noqa: BLE001 — hata task kaydina yazilir
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["error"] = str(e)


# --------------------------------------------------------------------------- #
# Geri bildirim (v0.6.0) — self-improvement cark'inin YAKIT sinyali.
#
# UI'da 👍/👎 -> POST /tasks/{session_id}/feedback. .quantumlabs/feedback.jsonl'e
# append (append_event deseniyle ayni; kalici, dedup yok — son karar gecerli sayilir
# okuyan tarafca). Ileride veri kuratorlugu (SFT/DPO) bu dosyayi kullanir.
# --------------------------------------------------------------------------- #
def _feedback_path(workspace: str) -> str:
    return os.path.join(workspace, _TRANSCRIPT_SUBDIR, "..", "feedback.jsonl")


class FeedbackRequest(BaseModel):
    rating: str                      # "up" | "down"
    note: Optional[str] = None
    workspace: Optional[str] = None


@app.post("/tasks/{session_id}/feedback")
def submit_feedback(session_id: str, req: FeedbackRequest):
    rating = (req.rating or "").strip().lower()
    if rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating 'up' ya da 'down' olmali")
    workspace = req.workspace or DEFAULT_WORKSPACE
    rec = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": session_id,
        "rating": rating,
        "note": (req.note or "")[:2000],
    }
    path = os.path.normpath(_feedback_path(workspace))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"feedback yazilamadi: {e}")
    return {"status": "ok", "session_id": session_id, "rating": rating}


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


def _live_gen(rec: dict, path: str, after_lines: int = 0):
    """CANLI session: transcript'i tail eder, approval sinyali + end yollar.

    after_lines: istemci ilk `after_lines` transcript satirini ZATEN gordu (ayni
    EventSource'u follow-up'ta yeniden bagladi) -> onlari atla, sadece yeni
    satirlari yolla. 0 (default) -> bastan tam replay + tail (yeni sayfa yuklemesi)."""
    pos = 0
    waited = 0
    sent_approval = None   # ayni approval_id icin BIR KEZ approval_needed yolla
    # transcript dosyasi henuz yoksa kisa bekle-yeniden-dene (~15s tavan).
    while not os.path.exists(path) and rec["status"] not in ("done", "failed") and waited < 50:
        time.sleep(0.3)
        waited += 1
    # after_lines: ilk N satiri atla, pos'u onlarin sonuna kaydir (tekrar gonderme).
    if after_lines and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for _ in range(after_lines):
                if not f.readline():
                    break
            pos = f.tell()
    idle_ticks = 0   # veri akmayan ardisik dongu sayisi (keepalive icin)
    while True:
        yielded = False
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
                    yielded = True
        pend = rec.get("pending_approval")
        if rec["status"] == "waiting_approval" and pend and pend["approval_id"] != sent_approval:
            sent_approval = pend["approval_id"]
            yield f"event: approval_needed\ndata: {json.dumps(pend, ensure_ascii=False)}\n\n"
            yielded = True
        if finished:                            # son satirlari attik, kapat
            end = {"status": rec["status"], "result": rec["result"], "error": rec["error"]}
            yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
            break
        # KEEPALIVE: cold-start / approval bekleyisi gibi uzun sessizliklerde bagli
        # kalsin. Bosta ~9s'de bir SSE yorumu (`:`) yolla -> tarayici/proxy idle
        # baglantiyi DUSURMEZ, boylece stale after=0 ile auto-reconnect + replay
        # (tekrar bug'i) hic tetiklenmez. Yorum satiri EventSource'ta yok sayilir.
        idle_ticks = 0 if yielded else idle_ticks + 1
        if idle_ticks >= 30:                     # ~30 * 0.3s = 9s
            idle_ticks = 0
            yield ": keepalive\n\n"
        time.sleep(0.3)


def _replay_gen(path: str, after_lines: int = 0):
    """S5: surec-oncesi / tamamlanmis session -> DISKTEN salt-okunur replay.

    Satir satir okur (tum sessionlar bellege YUKLENMEZ), bozuk/yarim jsonl
    satirlarini atlar, sonra event:end yollar. RESUME/tail YOK — tamamlanmis
    session tekrar canli akmaz; sadece transcript'i gosterir.

    after_lines: istemci ilk N transcript satirini zaten gordu (reconnect resume)
    -> onlari atla. _live_gen ile ayni semantik: reconnect'te tekrar akmasin."""
    try:
        with open(path, encoding="utf-8") as f:
            seen = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)          # gecerli JSON mi?
                except json.JSONDecodeError:
                    continue                  # bozuk/yarim satir -> atla
                seen += 1
                if seen <= after_lines:       # zaten gorulen satir -> atla (resume)
                    continue
                yield f"data: {line}\n\n"
    except OSError:
        pass
    end = {"status": "done", "result": None, "error": None, "replayed": True}
    yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"


@app.get("/tasks/{ident}/stream")
def stream_task(ident: str, after: int = 0):
    # ident = CANLI task_id (kisa) VEYA session_id (transcript dosya adi, kalici).
    # after: istemcinin zaten gordugu transcript satir sayisi (follow-up reconnect).
    rec = TASKS.get(ident)
    if rec is None:
        # live bir session'in session_id'siyle mi cagrildi? Ayni session_id'ye ait
        # birden cok task olabilir (ilk tur + follow-up'lar) -> CALISAN olani (yoksa
        # en yenisini) sec; yoksa yanlislikla eski 'done' rec'e baglanip aninda
        # end yollariz.
        matches = [r for r in TASKS.values() if r.get("session_id") == ident]
        live = [r for r in matches if r["status"] not in ("done", "failed")]
        rec = (live or matches)[-1] if matches else None

    if rec is not None:                        # CANLI -> tail
        path = _transcript_path(rec["workspace"], rec["session_id"])
        return StreamingResponse(_live_gen(rec, path, after_lines=after),
                                 media_type="text/event-stream")

    # GECMIS (surec-oncesi / tamamlanmis): diskten salt-okunur replay (after resume).
    hist_path = _transcript_path(DEFAULT_WORKSPACE, ident)
    if os.path.exists(hist_path):
        return StreamingResponse(_replay_gen(hist_path, after_lines=after),
                                 media_type="text/event-stream")

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
