"""Gercek 5 tool'un fake_ctx (AutoApprover, tmp_workspace) ile davranisi."""
from tools import registry


def test_read_file(fake_ctx):
    obs = registry.dispatch("read_file", {"path": "hello.txt"}, fake_ctx)
    assert obs.ok is True
    assert "merhaba" in obs.content


def test_search_code(fake_ctx):
    # NOT: search_code global WORKSPACE'te arar (ctx.cwd degil — A1'de search.py'ye
    # dokunulmadi). Repo kokunde "ToolRegistry" gectigi icin en az 1 eslesme beklenir.
    obs = registry.dispatch("search_code", {"query": "ToolRegistry"}, fake_ctx)
    assert obs.ok is True
    assert "ToolRegistry" in obs.content


def test_write_file_creates(fake_ctx, tmp_workspace):
    # AutoApprover: onay prompt'u (input) CAGRILMAZ; asili kalmaz.
    obs = registry.dispatch("write_file", {"path": "yeni.txt", "content": "icerik\n"}, fake_ctx)
    assert obs.ok is True
    assert (tmp_workspace / "yeni.txt").read_text(encoding="utf-8") == "icerik\n"


def test_replace_text_changes(fake_ctx, tmp_workspace):
    obs = registry.dispatch(
        "replace_text", {"path": "hello.txt", "old": "merhaba", "new": "selam"}, fake_ctx
    )
    assert obs.ok is True
    assert (tmp_workspace / "hello.txt").read_text(encoding="utf-8") == "selam\n"


def test_run_command_echo(fake_ctx):
    # v0.5.1-a: run_command artik ctx.approver'a bagli (inline input SOKULDU).
    # fake_ctx.approver = AutoApprover -> onay otomatik, input monkeypatch GEREKMEZ.
    obs = registry.dispatch("run_command", {"command": "echo TEST_OK"}, fake_ctx)
    assert obs.ok is True
    assert "TEST_OK" in obs.content
