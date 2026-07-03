"""run_agent session/workspace izolasyonu (v0.5.0 S1a)."""
import json
import os

import agents.code_agent as ca
from runtime.session import Session

FINAL = '{"thought":"bitti","tool":"final","args":{"answer":"tamamdir"}}'


def _fake_ask(_messages, _cfg):
    return FINAL


def _transcripts(workspace):
    tdir = os.path.join(workspace, ".quantumlabs", "transcripts")
    return sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []


def _events(workspace, jsonl_name):
    path = os.path.join(workspace, ".quantumlabs", "transcripts", jsonl_name)
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def test_two_runs_isolated(tmp_path, monkeypatch):
    ws = str(tmp_path)
    monkeypatch.setattr(ca, "ask_model", _fake_ask)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)   # finally no-op

    s1 = Session(ws)
    s2 = Session(ws)
    # session_id zaman damgasi; iki ayri dosya icin farkli id sart -> elle ayir
    object.__setattr__(s2, "session_id", s1.session_id + "_b")

    ca.run_agent("gorev A", session=s1, workspace=ws, memory_injection=False)
    ca.run_agent("gorev B", session=s2, workspace=ws, memory_injection=False)

    assert s1.session_id != s2.session_id
    files = _transcripts(ws)
    assert len(files) == 2                                   # IKI AYRI jsonl
    assert f"{s1.session_id}.jsonl" in files
    assert f"{s2.session_id}.jsonl" in files

    # her dosya kendi gorevini icerir (karismamis)
    ev1 = _events(ws, f"{s1.session_id}.jsonl")
    ev2 = _events(ws, f"{s2.session_id}.jsonl")
    assert ev1[0]["type"] == "user" and ev1[0]["content"] == "gorev A"
    assert ev2[0]["type"] == "user" and ev2[0]["content"] == "gorev B"


def test_step_counters_independent(tmp_path, monkeypatch):
    ws = str(tmp_path)
    monkeypatch.setattr(ca, "ask_model", _fake_ask)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    s1, s2 = Session(ws), Session(ws)
    object.__setattr__(s2, "session_id", s1.session_id + "_b")

    ca.run_agent("A", session=s1, workspace=ws, memory_injection=False)
    # ikinci session TAZE -> step yine 0'dan; ilk oturumun step'i ikinciyi etkilemez
    assert s2.step == 0
    ca.run_agent("B", session=s2, workspace=ws, memory_injection=False)
    # her iki run tek 'final' adiminda bitti -> step 1'e ulasip durdu
    assert s1.step == 1 and s2.step == 1


def test_given_session_reused_not_recreated(tmp_path, monkeypatch):
    ws = str(tmp_path)
    monkeypatch.setattr(ca, "ask_model", _fake_ask)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    sess = Session(ws)
    ca.run_agent("gorev", session=sess, workspace=ws, memory_injection=False)
    # verilen session kullanildi -> onun dosyasi olustu
    assert f"{sess.session_id}.jsonl" in _transcripts(ws)


def test_final_answer_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "ask_model", _fake_ask)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    ret = ca.run_agent("gorev", session=Session(str(tmp_path)),
                       workspace=str(tmp_path), memory_injection=False)
    assert ret == "tamamdir"                                  # return kanit


def test_max_steps_returns_none(tmp_path, monkeypatch):
    # v0.5.2: duz metin artik FINAL sayiliyor; max-step'e ulasmak icin FARKLI
    # (final olmayan) valid action'lar uret (tekrar guard'i tetiklenmesin).
    n = {"i": 0}

    def fake(_m, _c):
        n["i"] += 1
        return json.dumps({"tool": "search_code", "args": {"query": f"benzersiz_q{n['i']}"}})

    monkeypatch.setattr(ca, "ask_model", fake)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    ret = ca.run_agent("gorev", max_steps=2, session=Session(str(tmp_path)),
                       workspace=str(tmp_path), memory_injection=False)
    assert ret is None
