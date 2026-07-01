"""QuantumLabs — Tool gozlemi (v0.3.0 R2): handler ciktisini tek tipe indirger.

ReAct dongusu her aracin ciktisini ayni sekilde gozlemleyebilsin diye, farkli
donus tipleri (str / dict / EditOutcome) tek bir ToolObservation'a normalize
edilir. normalize_tool_result KENDI ICINDE exception-safe DEGILDIR; sarmak
ToolRunner'in (tools/runner.py) isidir.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Union

from protocols.safety import EditOutcome

# Handler'larin dondurebilecegi ham tipler.
# NOT: Python 3.9 uyumu icin runtime alias'ta `str | dict` yerine Union kullanilir
# (PEP 604 `|` runtime'da ancak 3.10+'da calisir).
ToolResult = Union[str, dict, EditOutcome]

__all__ = ["ToolResult", "ToolObservation", "normalize_tool_result"]


@dataclass
class ToolObservation:
    ok: bool
    tool: str
    content: str
    raw: object | None = None
    error: str | None = None


def normalize_tool_result(tool_name: str, result: object) -> ToolObservation:
    """Ham handler ciktisini ToolObservation'a cevirir. (Exception-safe DEGIL.)"""
    if isinstance(result, EditOutcome):
        # Repodaki EditOutcome alanlari: applied / path / message (ayri .error yok).
        # message zaten hem basari hem red/hata metnini tasidigindan content odur;
        # error basarisizlikta message'tan turetilir.
        return ToolObservation(
            ok=result.applied,
            tool=tool_name,
            content=result.message,
            raw=result,
            error=None if result.applied else result.message,
        )
    if isinstance(result, str):
        return ToolObservation(ok=True, tool=tool_name, content=result, raw=result)
    # dict vb. — okunabilir JSON'a cevir.
    return ToolObservation(
        ok=True,
        tool=tool_name,
        content=json.dumps(result, ensure_ascii=False, indent=2),
        raw=result,
    )
