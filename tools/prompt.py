"""QuantumLabs — Prompt uretimi (v0.3.0 R4): tool listesini registry'den render eder.

SYSTEM_PROMPT'taki "Kullanabilecegin araclar:" bolumunun tool satirlari artik
elle yazilmaz; render_tool_list registry metadata'sindan uretir. Boylece tool
ekleyip cikardikca prompt otomatik senkron kalir.

Format (mevcut prompt'la birebir): her tool tek satir
    "- {name}({imza}): {description}"
imza: parametre ADLARI virgullerle; required=False olanlar sonuna "?" alir.
NOT: ToolParam.type ve .description KASITLI olarak gosterilmez (mevcut prompt
imzada sadece isim gosteriyordu).
"""
from __future__ import annotations

from tools.registry import ToolRegistry


def render_tool_list(reg: ToolRegistry) -> str:
    """registry.all() sirasinda, her tool icin tek satirlik aciklama uretir."""
    lines = []
    for tool in reg.all():
        sig = ", ".join(
            p.name + ("" if p.required else "?") for p in tool.params
        )
        lines.append(f"- {tool.name}({sig}): {tool.description}")
    return "\n".join(lines)
