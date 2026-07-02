"""agents/llm.py — env override (cagri-aninda okuma) + lazy client + temperature
kwargs davranisi (v0.3.2 A3.0/A3.1)."""
from types import SimpleNamespace

import agents.llm as llm
from agents.llm import ModelConfig, ask_model


class _RecordingClient:
    """create(**kwargs)'i kaydeden sahte client (gercek OpenAI/Ollama'ya gitmez)."""

    def __init__(self, rec):
        def _create(**kwargs):
            rec.update(kwargs)
            msg = SimpleNamespace(content="sahte cevap")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def test_default_config_is_lazy():
    """Sadece import: hicbir client kurulmamali."""
    assert llm.get_client.cache_info().misses == 0


def test_temperature_none_omitted(monkeypatch):
    rec = {}
    monkeypatch.setattr(llm, "get_client", lambda cfg: _RecordingClient(rec))
    cfg = ModelConfig(base_url="b", api_key="k", model="m", temperature=None)
    out = ask_model([{"role": "user", "content": "x"}], cfg)
    assert out == "sahte cevap"
    assert "temperature" not in rec      # None -> gonderilmedi
    assert rec["model"] == "m"


def test_temperature_value_sent(monkeypatch):
    rec = {}
    monkeypatch.setattr(llm, "get_client", lambda cfg: _RecordingClient(rec))
    cfg = ModelConfig(base_url="b", api_key="k", model="m", temperature=0.2)
    ask_model([{"role": "user", "content": "x"}], cfg)
    assert rec["temperature"] == 0.2


def test_real_client_cache_untouched():
    """Sahte client testleri gercek lru_cache'li get_client'i cagirmadi."""
    assert llm.get_client.cache_info().misses == 0


def test_agent_imports_no_client():
    """chat_agent + simple_agent import'u client KURMAMALI (modul-seviyesi client kalkti)."""
    import agents.chat_agent  # noqa: F401
    import agents.simple_agent  # noqa: F401
    assert llm.get_client.cache_info().misses == 0


def test_env_override_model(monkeypatch):
    """default_config() env'i cagri aninda okur -> reload GEREKMEZ; client kurulmaz."""
    monkeypatch.setenv("QL_MODEL", "fake")
    assert llm.default_config().model == "fake"

    monkeypatch.delenv("QL_MODEL", raising=False)
    assert llm.default_config().model == "deepseek-coder-v2:16b"

    assert llm.get_client.cache_info().misses == 0   # hicbir client kurulmadi
