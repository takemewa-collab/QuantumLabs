"""QuantumLabs — pytest fixtures (v0.3.1 A2.1).

Bugun elle dogruladigimiz ctx-wiring / approver / guvenlik davranislarini
kalicilastiran testlerin ortak altyapisi. Kod degistirilmez; safety.py'ye
DenyApprover EKLENMEZ — burada yerel tanimlanir.
"""
import os
import sys
from types import SimpleNamespace

import pytest

# pyproject pythonpath=["."] zaten repo kokunu ekliyor; yine de garanti olsun.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from protocols.safety import ApprovalResult, AutoApprover  # noqa: E402
from tools import load_tools  # noqa: E402


class DenyApprover:
    """Her onay istegini REDDEDER (AutoApprover'in tersi).

    safety.py'ye eklenmedi — sadece testte guvenlik davranisini surmek icin."""

    def request(self, proposal):
        return ApprovalResult.deny("test: her sey reddedildi")


@pytest.fixture(scope="session", autouse=True)
def _registry_loaded():
    """Tum test oturumu icin registry'yi bir kez doldur (idempotent)."""
    load_tools()


@pytest.fixture
def tmp_workspace(tmp_path):
    """tmp_path tabanli gecici calisma dizini + birkac ornek dosya."""
    (tmp_path / "hello.txt").write_text("merhaba\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "ornek.py").write_text("x = 'ToolRegistry'  # ornek satir\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def fake_ctx(tmp_workspace):
    """Handler yolunun A1 ctx'i: cwd + otomatik-onaylayan approver, checkpoint yok."""
    return SimpleNamespace(
        cwd=str(tmp_workspace),
        approver=AutoApprover(),
        git_diff=lambda p: "(git yok)",
        session=None,
    )


@pytest.fixture
def deny_ctx(tmp_workspace):
    """fake_ctx ile ayni ama her yazma onayini REDDEDen approver."""
    return SimpleNamespace(
        cwd=str(tmp_workspace),
        approver=DenyApprover(),
        git_diff=lambda p: "(git yok)",
        session=None,
    )
