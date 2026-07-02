"""tools/memory.py — search_memory registry tool (v0.4.0 B3b)."""
import os
import subprocess
import sys
from types import SimpleNamespace

from runtime.memory_ingest import ingest_session
from runtime.transcript import append_event
from tools import registry


def test_search_memory_registered():
    assert "search_memory" in registry
    tool = registry.get("search_memory")
    assert [p.name for p in tool.params] == ["query", "top_k"]
    assert tool.params[0].required is True
    assert tool.params[1].required is False       # top_k opsiyonel


def test_empty_memory_ok(fake_ctx):
    obs = registry.dispatch("search_memory", {"query": "herhangi bir sey"}, fake_ctx)
    assert obs.ok is True                          # bos hafiza HATA degil
    assert "kayit yok" in obs.content


def test_search_returns_relevant(tmp_path):
    ws = str(tmp_path)
    sid = "2026-07-02_memtool"
    s = SimpleNamespace(workspace=ws, session_id=sid, step=0)
    append_event(s, {"type": "user", "content": "guvenlik onayini test et"})
    s.step = 1
    append_event(s, {"type": "assistant",
                     "content": '{"thought":"komut calistirmam gerek","tool":"run_command"}'})
    append_event(s, {"type": "observation", "tool": "run_command", "ok": False,
                     "content": "Kullanici komut calistirmayi reddetti"})
    assert ingest_session(sid, ws) >= 1

    ctx = SimpleNamespace(cwd=ws)
    obs = registry.dispatch("search_memory", {"query": "komut reddedildi mi", "top_k": 2}, ctx)
    assert obs.ok is True
    assert obs.content.startswith("[")             # "[skor] (...)" formati
    assert "reddet" in obs.content.lower()         # ilgili chunk geldi
    assert "adim" in obs.content                    # step formati


def test_lazy_import():
    """import tools.memory -> sentence_transformers/chromadb YUKLENMEZ (ayri surec)."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys, tools.memory\n"
            "assert 'sentence_transformers' not in sys.modules, 'ST erken'\n"
            "assert 'chromadb' not in sys.modules, 'chroma erken'\n"
            "print('lazy ok')\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=repo)
    assert r.returncode == 0, r.stderr
    assert "lazy ok" in r.stdout
