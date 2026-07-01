"""QuantumLabs — Arama araci (v0.3.0 R2): search_code.

Mantik agents/code_agent.py'deki tool_search_code'dan AYNEN tasindi; sadece
imza (args, ctx) oldu ve registry'ye kaydediliyor. Paylasilan WORKSPACE
code_agent'tan alinir (davranis degismez).
"""
from __future__ import annotations

import subprocess

from agents.code_agent import WORKSPACE
from tools.registry import ToolParam, registry


@registry.tool(
    name="search_code",
    description=(
        "repoda kod/metin arar (rg/grep). file_type ile uzantiya gore suz "
        '(orn "py"), max_results ile satir sayisini sinirla, files_only=True '
        "ile sadece eslesen dosya adlarini al. Repoyu anlamanin en hizli yolu budur."
    ),
    params=(
        ToolParam(name="query", type="string", description="aranacak metin/kod (grep gibi)"),
        ToolParam(name="file_type", type="string",
                  description='uzantiya gore suz, orn "py"', required=False),
        ToolParam(name="max_results", type="integer",
                  description="gosterilecek max satir (varsayilan 40)", required=False),
        ToolParam(name="files_only", type="boolean",
                  description="True ise sadece eslesen dosya adlarini dondurur", required=False),
    ),
)
def search_code(args: dict, ctx) -> str:
    query = args["query"]
    file_type = args.get("file_type")          # orn "py" -> sadece .py dosyalari
    max_results = args.get("max_results", 40)   # gosterilecek max satir
    files_only = args.get("files_only", False)  # True -> sadece eslesen dosya adlari

    has_rg = subprocess.run(
        "command -v rg", shell=True, capture_output=True, text=True
    ).stdout.strip()
    if has_rg:
        # rg .gitignore'a zaten saygi duyar; uretilen yedek/sanal-env klasorlerini
        # ayrica disla.
        cmd = ["rg", "--no-heading",
               "--glob", "!.quantumlabs/**", "--glob", "!.venv/**"]
        cmd.append("-l" if files_only else "-n")
        if file_type:
            cmd += ["-t", file_type]
        cmd += [query, WORKSPACE]
    else:
        cmd = ["grep", "-rl" if files_only else "-rn"]
        if file_type:
            cmd.append(f"--include=*.{file_type}")
        cmd += [query, WORKSPACE]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "HATA: arama 20 saniyede bitmedi."
    out = result.stdout.strip().replace(WORKSPACE + "/", "")
    if not out:
        return f"'{query}' icin eslesme bulunamadi."
    # Karakter degil SATIR bazli sinirla (kelime/yol ortasindan kesme yok).
    lines = out.split("\n")
    total = len(lines)
    if total > max_results:
        shown = "\n".join(lines[:max_results])
        return (f"{shown}\n\nToplam {total} eslesme bulundu, ilk {max_results} "
                f"gosteriliyor. Daraltmak icin daha spesifik bir query ya da "
                f"file_type kullan.")
    return out
