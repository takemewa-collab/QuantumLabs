"""runtime/transcript.py — best-effort jsonl yazma (v0.4.0 B2)."""
import json
import os
import stat
from types import SimpleNamespace

import pytest

from runtime.transcript import append_event


def _session(workspace):
    # transcript yalnizca workspace + session_id + step okur (duck typing).
    return SimpleNamespace(workspace=str(workspace), session_id="2026-07-02_120000", step=0)


def _transcript_path(workspace, sess):
    return os.path.join(str(workspace), ".quantumlabs", "transcripts", f"{sess.session_id}.jsonl")


def test_append_creates_file_valid_json(tmp_path):
    sess = _session(tmp_path)
    append_event(sess, {"type": "user", "content": "merhaba"})

    path = _transcript_path(tmp_path, sess)
    assert os.path.exists(path)
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["type"] == "user"
    assert ev["content"] == "merhaba"
    assert "ts" in ev and "step" in ev and ev["session_id"] == sess.session_id


def test_three_events_order_preserved(tmp_path):
    sess = _session(tmp_path)
    append_event(sess, {"type": "user", "content": "gorev"})
    sess.step = 1
    append_event(sess, {"type": "assistant", "content": "yanit"})
    append_event(sess, {"type": "observation", "tool": "read_file", "ok": True, "content": "veri"})

    lines = open(_transcript_path(tmp_path, sess), encoding="utf-8").read().splitlines()
    assert len(lines) == 3
    types = [json.loads(x)["type"] for x in lines]
    assert types == ["user", "assistant", "observation"]
    assert json.loads(lines[1])["step"] == 1


def test_observation_content_truncated(tmp_path):
    sess = _session(tmp_path)
    big = "x" * 2500
    append_event(sess, {"type": "observation", "tool": "read_file", "ok": True, "content": big})

    ev = json.loads(open(_transcript_path(tmp_path, sess), encoding="utf-8").read().splitlines()[0])
    assert len(ev["content"]) == 2000
    assert ev["truncated"] is True


def test_non_observation_not_truncated(tmp_path):
    sess = _session(tmp_path)
    big = "y" * 2500
    append_event(sess, {"type": "assistant", "content": big})

    ev = json.loads(open(_transcript_path(tmp_path, sess), encoding="utf-8").read().splitlines()[0])
    assert len(ev["content"]) == 2500
    assert "truncated" not in ev


def test_unwritable_dir_does_not_raise(tmp_path, capsys):
    # transcripts dizinini onceden olustur + salt-okunur yap -> open("a") patlar
    tdir = tmp_path / ".quantumlabs" / "transcripts"
    tdir.mkdir(parents=True)
    tdir.chmod(stat.S_IREAD | stat.S_IEXEC)   # yazma yok
    sess = _session(tmp_path)
    try:
        # exception SIZMAMALI (best-effort) — cagri sessizce donmeli
        append_event(sess, {"type": "user", "content": "x"})
    finally:
        tdir.chmod(stat.S_IRWXU)  # cleanup icin geri ac
    err = capsys.readouterr().err
    assert "[transcript]" in err   # stderr'e uyari dustu
