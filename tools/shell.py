"""QuantumLabs — Kabuk/okuma araclari (v0.3.1 A1): read_file, run_command.

Ikisi de calisma dizinini artik ctx.cwd'den alir (modul-global WORKSPACE yerine).
run_command onayi DEGISMEDI: inline input() oldugu gibi. Genel/komut onayini
Approver'a baglamak icin proposal modelinin genisletilmesi gerekiyor -> CommandProposal
ile ayri adimda (A1 disi).
"""
from __future__ import annotations

import os
import subprocess

from agents.code_agent import BLOCKED_COMMANDS, _safe_path
from tools.registry import ToolParam, registry


@registry.tool(
    name="read_file",
    description="bir dosyanin icerigini okur.",
    params=(
        ToolParam(name="path", type="string", description="okunacak dosya yolu (goreceli)"),
    ),
)
def read_file(args: dict, ctx) -> str:
    path = _safe_path(args["path"], ctx.cwd)
    if not os.path.exists(path):
        return f"HATA: dosya bulunamadi: {args['path']}"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    if len(content) > 6000:
        content = content[:6000] + "\n... [dosya kirpildi] ..."
    return content


@registry.tool(
    name="run_command",
    description="bir kabuk komutu calistirir (git, pytest, python vb.).",
    params=(
        ToolParam(name="command", type="string",
                  description="calistirilacak kabuk komutu"),
    ),
)
def run_command(args: dict, ctx) -> str:
    command = args["command"]
    for bad in BLOCKED_COMMANDS:
        if bad in command:
            return f"HATA: tehlikeli komut engellendi ('{bad}' iceriyor)."
    # run_command onayı CommandProposal ile ayrı adımda (A1 dışı); simdilik inline input.
    print(f"\n  [!] Agent su komutu calistirmak istiyor:\n      {command}")
    if input("  Onayliyor musun? [e/h]: ").strip().lower() != "e":
        return "Kullanici komut calistirmayi reddetti."
    try:
        result = subprocess.run(
            command, shell=True, cwd=ctx.cwd,
            capture_output=True, text=True, timeout=30,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out.strip()[:4000] or "(komut cikti uretmedi)"
    except subprocess.TimeoutExpired:
        return "HATA: komut 30 saniyede bitmedi (zaman asimi)."
