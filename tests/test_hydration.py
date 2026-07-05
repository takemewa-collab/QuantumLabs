"""S5 — surec-oncesi/tamamlanmis session'lari diskten salt-okunur replay."""
import json

from fastapi.testclient import TestClient

import api.main as main
from api.main import app

client = TestClient(app)


def _write(tmp_path, session_id, lines):
    tdir = tmp_path / ".quantumlabs" / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / f"{session_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_historical_replay_read_only(tmp_path, monkeypatch):
    # TASKS bos (surec yeni basladi/yeniden basladi) — sadece diskte transcript var.
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(main, "TASKS", {})
    sid = "2026-07-05_101112_dead1234"
    _write(tmp_path, sid, [
        json.dumps({"type": "user", "content": "summarize README", "ts": "2026-07-05T10:11:12+00:00"}),
        json.dumps({"type": "assistant", "content": '{"tool":"read_file"}', "ts": "t1"}),
        json.dumps({"type": "observation", "tool": "read_file", "ok": True, "content": "# Quantum Labs"}),
    ])
    with client.stream("GET", f"/tasks/{sid}/stream") as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    # tum transcript satirlari data: olarak geldi + kapanis event:end (replayed)
    assert body.count("data:") >= 3
    assert "summarize README" in body
    assert "# Quantum Labs" in body
    assert "event: end" in body
    assert '"replayed": true' in body


def test_replay_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(main, "TASKS", {})
    sid = "2026-07-05_101113_corrupt0"
    _write(tmp_path, sid, [
        json.dumps({"type": "user", "content": "hi"}),
        '{"type": "assistant", "content": "yarim',        # bozuk/yarim JSON
        json.dumps({"type": "done"}),
    ])
    with client.stream("GET", f"/tasks/{sid}/stream") as r:
        body = "".join(r.iter_text())
    assert "yarim" not in body                 # bozuk satir atlandi
    assert '"content": "hi"' in body           # gecerli satirlar geldi
    assert '"type": "done"' in body
    assert "event: end" in body


def test_unknown_session_404(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(main, "TASKS", {})
    assert client.get("/tasks/olmayan_session/stream").status_code == 404


def test_pre_restart_session_lists_and_opens(tmp_path, monkeypatch):
    # "restart" senaryosu: TASKS bos ama disk'te transcript var -> hem listede hem acilir.
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(main, "TASKS", {})
    sid = "2026-07-05_101114_beef5678"
    _write(tmp_path, sid, [json.dumps({"type": "user", "content": "old task", "ts": "2026-07-05T10:11:14+00:00"})])

    listed = client.get("/sessions").json()
    assert any(s["id"] == sid and s["title"] == "old task" for s in listed)   # listeleniyor
    with client.stream("GET", f"/tasks/{sid}/stream") as r:
        assert r.status_code == 200                                          # aciliyor (404 degil)
        assert "old task" in "".join(r.iter_text())
