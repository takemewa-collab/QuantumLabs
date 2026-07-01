"""QuantumLabs — ToolRunner (v0.3.0 R2): handler'i guvenli calistirir.

run_tool, hem handler'in kendisini hem de normalize adimini try/except ile
sarar; boylece bir aracin patlamasi ReAct dongusunu dusurmez, temiz bir
ToolObservation (ok=False) gozlemi olur.
"""
from __future__ import annotations

from tools.observation import ToolObservation, normalize_tool_result

__all__ = ["run_tool"]


def run_tool(tool, args: dict, ctx) -> ToolObservation:
    try:
        result = tool.handler(args, ctx)
    except Exception as e:
        return ToolObservation(
            ok=False,
            tool=tool.name,
            content=f"{tool.name} hata verdi: {e}",
            error=str(e),
        )
    try:
        return normalize_tool_result(tool.name, result)
    except Exception as e:
        return ToolObservation(
            ok=False,
            tool=tool.name,
            content=f"sonuç normalize edilemedi: {e}",
            raw=result,
            error=str(e),
        )
