"""Production config — CORS origins + optional API key auth."""
import json

from fastapi.testclient import TestClient

import api.main as main
from api.main import app

client = TestClient(app)


def test_allowed_origins_default(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert main._allowed_origins() == ["http://localhost:3000"]


def test_allowed_origins_comma_split(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.com, https://b.com ,")
    assert main._allowed_origins() == ["https://a.com", "https://b.com"]


def test_cors_preflight_allowed_for_dev_origin():
    r = client.options(
        "/tasks",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- Optional API key (API_KEY env) ---------------------------------------- #
def test_no_auth_when_key_unset(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert client.get("/sessions").status_code == 200          # bugunku davranis


def test_auth_required_when_key_set(monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    assert client.get("/sessions").status_code == 401                                  # header yok
    assert client.get("/sessions", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/sessions", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_sse_auth_via_query_key(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    monkeypatch.setattr(main, "DEFAULT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(main, "TASKS", {})
    tdir = tmp_path / ".quantumlabs" / "transcripts"
    tdir.mkdir(parents=True)
    sid = "2026-07-05_000000_authkey0"
    (tdir / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "content": "x"}) + "\n", encoding="utf-8")
    # EventSource header gonderemez -> query'siz 401, ?key= ile 200
    assert client.get(f"/tasks/{sid}/stream").status_code == 401
    with client.stream("GET", f"/tasks/{sid}/stream?key=s3cret") as r:
        assert r.status_code == 200
