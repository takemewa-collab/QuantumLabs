"""Model config secimi: acik param > Session.model_config > env default + QUANTUM_POD."""
import agents.code_agent as ca
from agents.llm import ModelConfig, QUANTUM_POD, default_config, quantum_pod_config
from runtime.session import Session

CUSTOM = ModelConfig(base_url="http://x/v1", api_key="k", model="m-custom")
OTHER = ModelConfig(base_url="http://y/v1", api_key="k2", model="m-explicit")


def _capture_cfg(monkeypatch):
    got = {}

    def fake(messages, cfg):
        got["cfg"] = cfg
        return '{"tool":"final","args":{"answer":"ok"}}'

    monkeypatch.setattr(ca, "ask_model", fake)
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)
    return got


def test_session_model_config_is_used(tmp_path, monkeypatch):
    got = _capture_cfg(monkeypatch)
    sess = Session(str(tmp_path), model_config=CUSTOM)
    ca.run_agent("gorev", session=sess, workspace=str(tmp_path),
                 memory_injection=False, max_steps=2)
    assert got["cfg"] is CUSTOM


def test_explicit_param_overrides_session(tmp_path, monkeypatch):
    got = _capture_cfg(monkeypatch)
    sess = Session(str(tmp_path), model_config=CUSTOM)
    ca.run_agent("gorev", session=sess, workspace=str(tmp_path),
                 model_config=OTHER, memory_injection=False, max_steps=2)
    assert got["cfg"] is OTHER            # acik param > Session


def test_default_when_no_config(tmp_path, monkeypatch):
    got = _capture_cfg(monkeypatch)
    sess = Session(str(tmp_path))          # model_config=None
    ca.run_agent("gorev", session=sess, workspace=str(tmp_path),
                 memory_injection=False, max_steps=2)
    assert got["cfg"].model == default_config().model   # env default'a duser


def test_quantum_pod_config_env(monkeypatch):
    monkeypatch.setenv("QUANTUM_POD_BASE_URL", "https://pod.example/v1")
    monkeypatch.setenv("QUANTUM_POD_MODEL", "pod-xyz")
    monkeypatch.setenv("QUANTUM_POD_API_KEY", "secret")
    cfg = quantum_pod_config()             # env'i cagri aninda okur
    assert cfg.base_url == "https://pod.example/v1"
    assert cfg.model == "pod-xyz"
    assert cfg.api_key == "secret"
    # QUANTUM_POD frozen ModelConfig -> get_client lru_cache anahtari olabilir
    assert isinstance(QUANTUM_POD, ModelConfig)
    assert hash(QUANTUM_POD) == hash(QUANTUM_POD)


def test_session_model_config_defaults_none():
    # geriye uyumluluk: model_config vermeden Session -> None
    assert Session("/tmp").model_config is None
