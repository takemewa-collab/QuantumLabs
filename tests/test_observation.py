"""normalize_tool_result'in uc dali + ToolRunner'in exception yolu.

Hepsi run_tool uzerinden test edilir (gercek dispatch yolu): handler ciktisi ne
olursa olsun ReAct dongusu temiz bir ToolObservation gorur, exception disari sizmaz.
"""
from types import SimpleNamespace

from protocols.safety import EditOutcome
from tools.runner import run_tool


def _tool(name, fn):
    """run_tool'un bekledigi minimal tool: .name + .handler(args, ctx)."""
    return SimpleNamespace(name=name, handler=fn)


def test_str_result():
    obs = run_tool(_tool("t", lambda a, c: "duz metin"), {}, None)
    assert obs.ok is True
    assert obs.content == "duz metin"


def test_dict_result_json():
    obs = run_tool(_tool("t", lambda a, c: {"a": 1, "b": "iki"}), {}, None)
    assert obs.ok is True
    assert '"a": 1' in obs.content        # json.dumps(indent=2)
    assert '"b": "iki"' in obs.content


def test_edit_outcome_applied_true():
    eo = EditOutcome(True, "x.py", "yazildi")
    obs = run_tool(_tool("write_file", lambda a, c: eo), {}, None)
    assert obs.ok is True
    assert obs.content == "yazildi"


def test_edit_outcome_applied_false_content_has_error():
    # invariant: agent hatayi content'te gorur
    eo = EditOutcome(False, "x.py", "HATA: dosya yok")
    obs = run_tool(_tool("write_file", lambda a, c: eo), {}, None)
    assert obs.ok is False
    assert "HATA" in obs.content


def test_handler_raises_is_caught():
    def boom(a, c):
        raise RuntimeError("patladim")

    obs = run_tool(_tool("boom", boom), {}, None)
    assert obs.ok is False
    assert "boom" in obs.content and "patladim" in obs.content


def test_unserializable_result_does_not_crash():
    # set JSON'a serialize edilemez -> normalize iceride patlar, run_tool yakalar
    obs = run_tool(_tool("t", lambda a, c: {1, 2, 3}), {}, None)
    assert obs.ok is False
    assert "normalize edilemedi" in obs.content
