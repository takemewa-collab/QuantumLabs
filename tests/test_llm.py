"""agents/llm.py — env override (cagri-aninda okuma) + lazy client (v0.3.2 A3.0)."""
import agents.llm as llm


def test_default_config_is_lazy():
    """Sadece import: hicbir client kurulmamali."""
    assert llm.get_client.cache_info().misses == 0


def test_env_override_model(monkeypatch):
    """default_config() env'i cagri aninda okur -> reload GEREKMEZ; client kurulmaz."""
    monkeypatch.setenv("QL_MODEL", "fake")
    assert llm.default_config().model == "fake"

    monkeypatch.delenv("QL_MODEL", raising=False)
    assert llm.default_config().model == "deepseek-coder-v2:16b"

    assert llm.get_client.cache_info().misses == 0   # hicbir client kurulmadi
