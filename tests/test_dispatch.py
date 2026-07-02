"""registry.dispatch temel davranisi + import yan-etkisi guvencesi."""
from tools import registry

EXPECTED_TOOLS = {"read_file", "search_code", "write_file", "replace_text",
                  "run_command", "search_memory"}


def test_unknown_tool(fake_ctx):
    obs = registry.dispatch("yok_boyle", {}, fake_ctx)
    assert obs.ok is False
    assert "bilinmeyen" in obs.content.lower()


def test_all_tools_registered():
    assert len(registry) == 6
    assert {t.name for t in registry.all()} == EXPECTED_TOOLS


def test_no_llm_client_constructed():
    """A2.0 guvencesi: testler boyunca OpenAI/Ollama client'i HIC kurulmamali."""
    import agents.code_agent as ca
    assert ca.get_client.cache_info().misses == 0
