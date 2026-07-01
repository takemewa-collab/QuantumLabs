"""QuantumLabs — Duzenleme araclari (v0.3.1 A1): write_file, replace_text.

Guvenlik/onay/checkpoint hala SafeEditProtocol icinde; A1'de approver + cwd (+ session)
artik CTX'ten geliyor (import-time global _protocol yerine). Otomatik git diff de
ctx.git_diff uzerinden. Boylece bir handler'i cagiran, calisma-zamani baglamini
(hangi workspace, hangi approver) tamamen ctx ile kontrol eder.
"""
from __future__ import annotations

from protocols.safety import SafeEditProtocol
from tools.registry import ToolParam, registry


def _protocol_for(ctx) -> SafeEditProtocol:
    """ctx'ten approver + cwd (+ varsa session) ile bir SafeEditProtocol kurar.

    root=ctx.cwd: workspace-disina yazmayi engeller (v0.3.0'daki root=WORKSPACE ile ayni).
    session: varsa checkpoint (snapshot/atomic_write/accept); yoksa duz yazma.
    """
    return SafeEditProtocol(
        approver=ctx.approver,
        root=ctx.cwd,
        session=getattr(ctx, "session", None),
    )


@registry.tool(
    name="write_file",
    description="bir dosyaya bastan icerik yazar (uzerine yazar).",
    params=(
        ToolParam(name="path", type="string", description="yazilacak dosya yolu (goreceli)"),
        ToolParam(name="content", type="string", description="dosyaya bastan yazilacak icerik"),
    ),
)
def write_file(args: dict, ctx) -> str:
    outcome = _protocol_for(ctx).write_file(args["path"], args["content"])
    if not outcome.applied:
        return outcome.message
    diff = ctx.git_diff(args["path"])
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
    outcome = _protocol_for(ctx).replace_text(args["path"], args["old"], args["new"])
    if not outcome.applied:
        return outcome.message
    diff = ctx.git_diff(args["path"])
    return f"{outcome.message}\n\nGIT DIFF:\n{diff}"
