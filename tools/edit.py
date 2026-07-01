"""QuantumLabs — Duzenleme araclari (v0.3.0 R2): write_file, replace_text.

Mantik agents/code_agent.py'deki tool_write_file / tool_replace_text'ten AYNEN
tasindi. Guvenlik/onay/checkpoint tek instance olan _protocol icinde; degisiklik
sonrasi otomatik git diff icin _auto_git_diff korunur. Ikisi de code_agent'tan
alinir (davranis degismez).
"""
from __future__ import annotations

from agents.code_agent import _auto_git_diff, _protocol
from tools.registry import ToolParam, registry


@registry.tool(
    name="write_file",
    description="bir dosyaya bastan icerik yazar (uzerine yazar).",
    params=(
        ToolParam(name="path", type="string", description="yazilacak dosya yolu (goreceli)"),
        ToolParam(name="content", type="string", description="dosyaya bastan yazilacak icerik"),
    ),
)
def write_file(args: dict, ctx) -> str:
    outcome = _protocol.write_file(args["path"], args["content"])
    if not outcome.applied:
        return outcome.message
    diff = _auto_git_diff(args["path"])
    return f"{outcome.message}\n\nGIT DIFF:\n{diff}"


@registry.tool(
    name="replace_text",
    description=("bir dosyada 'old' metnini 'new' ile degistirir. Kucuk "
                 "degisiklikler icin write_file yerine BUNU tercih et."),
    params=(
        ToolParam(name="path", type="string", description="degisecek dosya yolu (goreceli)"),
        ToolParam(name="old", type="string", description="degistirilecek eski metin (benzersiz)"),
        ToolParam(name="new", type="string", description="yerine yazilacak yeni metin"),
    ),
)
def replace_text(args: dict, ctx) -> str:
    outcome = _protocol.replace_text(args["path"], args["old"], args["new"])
    if not outcome.applied:
        return outcome.message
    diff = _auto_git_diff(args["path"])
    return f"{outcome.message}\n\nGIT DIFF:\n{diff}"
