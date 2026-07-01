"""Bugun elle dogrulanan guvenlik davranislarinin kalici testleri:
approver reddi, workspace-disi kacis engeli, checkpoint'siz calisma.
"""
import os

from tools import registry


def test_deny_blocks_write(deny_ctx, tmp_workspace):
    obs = registry.dispatch(
        "write_file", {"path": "olmaz.txt", "content": "x"}, deny_ctx
    )
    # Handler reddi outcome.message olarak dondurur (str) -> gozlem "reddedildi" der.
    assert "reddedil" in obs.content.lower()
    # ASIL guvenlik ozelligi: dosya diske YAZILMADI.
    assert not (tmp_workspace / "olmaz.txt").exists()


def test_workspace_escape_blocked(fake_ctx, tmp_workspace):
    # 1) goreceli ".." ile disari
    rel_target = tmp_workspace.parent / "disari.txt"
    obs_rel = registry.dispatch(
        "write_file", {"path": "../disari.txt", "content": "x"}, fake_ctx
    )
    assert obs_rel.ok is False
    assert not rel_target.exists()

    # 2) mutlak yol ile disari
    obs_abs = registry.dispatch(
        "write_file", {"path": "/tmp/mutlak.txt", "content": "x"}, fake_ctx
    )
    assert obs_abs.ok is False
    assert not os.path.exists("/tmp/mutlak.txt")


def test_checkpoint_absent_ok(fake_ctx, tmp_workspace):
    # session=None: write basarili, checkpoint dizini olusmamasi hata uretmez.
    obs = registry.dispatch(
        "write_file", {"path": "ckptsiz.txt", "content": "veri\n"}, fake_ctx
    )
    assert obs.ok is True
    assert (tmp_workspace / "ckptsiz.txt").exists()
    assert not (tmp_workspace / ".quantumlabs").exists()
