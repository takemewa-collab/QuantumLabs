"""QuantumLabs — Tool yukleyici (v0.3.0 R2): tool modullerini import ederek kaydeder.

Tool modulleri import edildiginde @registry.tool dekoratorleri calisir ve
araclar singleton registry'ye kaydolur. load_tools() sadece bu import'lari
tetikler.
"""
from __future__ import annotations

import importlib

TOOL_MODULES = ["tools.search", "tools.edit", "tools.shell"]

__all__ = ["TOOL_MODULES", "load_tools"]


def load_tools() -> None:
    for mod in TOOL_MODULES:
        importlib.import_module(mod)
