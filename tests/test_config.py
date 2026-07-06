"""Production config — CORS origins from env (ALLOWED_ORIGINS)."""
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
