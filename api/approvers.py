"""QuantumLabs API — approver'lar (v0.5.1-a).

WebApprover: run_agent API'de BackgroundTask THREAD'inde koser; bir yazma/komut
onayi gerektiginde web kararini BEKLER (threading.Event). Karar gelmezse TIMEOUT
-> DENY (asili thread imkansiz — guvenli default).

DenyAllApprover: onaysiz her seyi reddeder (S1b default'uydu; artik yedek/opsiyon).

Paylasilan durum (tek worker, in-process): PENDING (bekleyen), RESOLVED (karar
verilmis; 409 tespiti). Cok worker'da paylasilmaz (S5).
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from protocols.safety import ApprovalResult, Decision

_LOCK = threading.Lock()
PENDING: dict = {}    # approval_id -> entry (payload + _event + _holder + resolved)
RESOLVED: dict = {}   # approval_id -> {approved, reason}   (409 + kisa gecmis)


class DenyAllApprover:
    """Her istegi reddeder. AutoApprover ASLA — web'de onaysiz yazma olmaz."""

    def request(self, proposal):
        return ApprovalResult.deny("web onay akisi henuz yok / DenyAll")


def _proposal_payload(proposal, kind: str) -> dict:
    if kind == "command":
        return {"command": proposal.command, "cwd": proposal.cwd}
    return {
        "path": proposal.path,
        "is_new_file": proposal.is_new_file,
        "summary": getattr(proposal, "summary", ""),
        "diff": None if proposal.is_new_file else proposal.unified_diff(),
        "new_content": proposal.new_content if proposal.is_new_file else None,
    }


def _serialize(entry: dict) -> dict:
    return {k: entry[k] for k in ("approval_id", "task_id", "kind", "payload", "resolved")}


def list_pending() -> list:
    with _LOCK:
        return [_serialize(e) for e in PENDING.values() if not e["resolved"]]


def get_pending(approval_id: str) -> Optional[dict]:
    with _LOCK:
        entry = PENDING.get(approval_id)
        return _serialize(entry) if entry else None


def resolve_approval(approval_id: str, approved: bool, reason: str = "") -> str:
    """Endpoint + testler icin ortak karar giris noktasi.

    Donus: 'ok' (karar islendi) | 'not_found' (hic yok) | 'already' (zaten kararli)."""
    with _LOCK:
        entry = PENDING.get(approval_id)
        if entry is None:
            return "already" if approval_id in RESOLVED else "not_found"
        if entry["resolved"]:
            return "already"
        entry["_holder"]["approved"] = bool(approved)
        entry["_holder"]["reason"] = reason
        entry["resolved"] = True
        entry["_event"].set()
        return "ok"


class WebApprover:
    """request(proposal) -> web kararini bekler; timeout -> DENY."""

    def __init__(self, task_id: str, tasks: dict, timeout_sec: float = 300):
        self.task_id = task_id
        self.tasks = tasks
        self.timeout_sec = timeout_sec

    def request(self, proposal) -> ApprovalResult:
        approval_id = uuid.uuid4().hex[:8]
        kind = getattr(proposal, "kind", "edit")
        payload = _proposal_payload(proposal, kind)
        event = threading.Event()
        holder: dict = {}
        entry = {"approval_id": approval_id, "task_id": self.task_id, "kind": kind,
                 "payload": payload, "resolved": False, "_event": event, "_holder": holder}
        with _LOCK:
            PENDING[approval_id] = entry
            rec = self.tasks.get(self.task_id)
            if rec is not None:
                rec["status"] = "waiting_approval"
                rec["pending_approval"] = {"approval_id": approval_id, "kind": kind, "payload": payload}

        got = event.wait(self.timeout_sec)   # <-- web kararini BEKLE (veya timeout)

        with _LOCK:
            PENDING.pop(approval_id, None)
            if got:
                approved = bool(holder.get("approved", False))
                reason = holder.get("reason", "") or ("web onay" if approved else "web reddetti")
            else:
                approved, reason = False, "onay zaman aşımı"   # TIMEOUT -> DENY
            RESOLVED[approval_id] = {"approved": approved, "reason": reason}
            rec = self.tasks.get(self.task_id)
            if rec is not None:
                rec["status"] = "running"
                rec["pending_approval"] = None

        decision = Decision.APPROVE if approved else Decision.DENY
        return ApprovalResult(decision, reason, approver="web")
