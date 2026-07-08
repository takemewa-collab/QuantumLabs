"""QuantumLabs — Kabuk/okuma araclari (read_file, run_command).

Ikisi de calisma dizinini ctx.cwd'den alir. run_command onayi artik ctx.approver
uzerinden (v0.5.1-a): inline input() SOKULDU -> terminalde TerminalApprover,
web'de WebApprover devreye girer; komut CommandProposal ile onaya sunulur.
BLOCKED_COMMANDS blacklist'i onaya DUSMEZ (once reddedilir).
"""
from __future__ import annotations

import fnmatch
import os
import subprocess

from agents.code_agent import BLOCKED_COMMANDS, _safe_path
from protocols.safety import CommandProposal
from tools.registry import ToolParam, registry


@registry.tool(
    name="list_files",
    description=(
        "bir dizindeki dosya/klasorleri listeler. path verilmezse calisma dizini. "
        "pattern ile glob suz (orn '*.py'). DOSYA/DIZIN LISTELEMEK icin BUNU kullan "
        "— search_code icerik arar, listelemez."
    ),
    params=(
        ToolParam(name="path", type="string",
                  description="dizin yolu (goreceli); varsayilan '.'", required=False),
        ToolParam(name="pattern", type="string",
                  description="glob suzgeci, orn '*.py'", required=False),
    ),
)
def list_files(args: dict, ctx) -> str:
    rel = args.get("path") or "."
    path = _safe_path(rel, ctx.cwd)
    if not os.path.exists(path):
        return f"HATA: yol bulunamadi: {rel}"
    if not os.path.isdir(path):
        return f"HATA: dizin degil: {rel}"
    pattern = args.get("pattern")
    try:
        entries = sorted(os.listdir(path))
    except OSError as e:  # noqa: BLE001
        return f"HATA: listelenemedi: {e}"
    names = []
    for name in entries:
        if pattern and not fnmatch.fnmatch(name, pattern):
            continue
        names.append(name + ("/" if os.path.isdir(os.path.join(path, name)) else ""))
    if not names:
        suffix = f" ('{pattern}' desenine uyan)" if pattern else ""
        return f"'{rel}' dizininde dosya yok{suffix}."
    return "\n".join(names)


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
    # 1) Blacklist ONAYA DUSMEZ: tehlikeli komut dogrudan reddedilir.
    for bad in BLOCKED_COMMANDS:
        if bad in command:
            return f"HATA: tehlikeli komut engellendi ('{bad}' iceriyor)."
    # 2) Onay: ctx.approver (terminal/web) -> CommandProposal.
    decision = ctx.approver.request(CommandProposal(command=command, cwd=ctx.cwd))
    if not decision.approved:
        return f"Kullanici komut calistirmayi reddetti ({decision.reason})."
    try:
        result = subprocess.run(
            command, shell=True, cwd=ctx.cwd,
            capture_output=True, text=True, timeout=30,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out.strip()[:4000] or "(komut cikti uretmedi)"
    except subprocess.TimeoutExpired:
        return "HATA: komut 30 saniyede bitmedi (zaman asimi)."
