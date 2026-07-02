"""QuantumLabs — Kod Agent'i (v4): degisiklik sonrasi OTOMATIK git diff (kodla zorlanir)."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from types import SimpleNamespace

# code_agent.py agents/ altinda; protocols/ repo kokunde. Repo kokunu sys.path'e ekle.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import ask_model, default_config, get_client  # noqa: F401 (get_client: lazy-guard testleri)
from protocols.safety import SafeEditProtocol, TerminalApprover
from runtime.session import Session
from runtime.transcript import append_event
from tools import load_tools, registry
from tools.prompt import render_tool_list

# Model/endpoint konfigurasyonu + client + ask_model artik agents/llm.py'de
# (ortak LLM katmani). code_agent varsayilan olarak DEFAULT_CONFIG kullanir;
# run_agent'a model_config vererek override edilebilir.


WORKSPACE = os.path.abspath(os.getcwd())

# Tum guvenlik mantigi (diff, onay, count kontrolu, path kilidi, dosya yazma)
# burada yasiyor. Tool'lar sadece bu instance'a delege eder.
# Session verince yazma islemleri checkpoint'lenir (snapshot + rollback altyapisi).
session = Session(WORKSPACE)
_protocol = SafeEditProtocol(approver=TerminalApprover(), root=WORKSPACE, session=session)

BLOCKED_COMMANDS = [
    "rm -rf", "rm -fr", "sudo", "mkfs", "shutdown", "reboot",
    ":(){", "chmod -R 777", "> /dev/sda", "dd if=", "--no-preserve-root",
]

def _safe_path(path, cwd):
    """Yolu verilen calisma dizinine (cwd) kilitler (commonpath; startswith guvenilmez)."""
    full = os.path.abspath(os.path.join(cwd, path))
    if os.path.commonpath([cwd, full]) != cwd:
        raise ValueError(f"Guvenlik: calisma dizini disina erisim engellendi: {path}")
    return full


def _auto_git_diff(path, cwd):
    """Bir dosya degistikten sonra otomatik calisir. Framework garantisi:
    degisikligi gormek modelin insafina birakilmaz, kodla zorlanir. cwd: git deposu koku."""
    try:
        status = subprocess.run(
            "git status --short -- " + shlex.quote(path),
            shell=True, cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        st = status.stdout.strip()
        if not st:
            if not os.path.isdir(os.path.join(cwd, ".git")):
                return "(git deposu degil; diff atlandi)"
            return "(degisiklik git tarafindan gorulmedi)"
        if st.startswith("??"):
            return f"(yeni dosya, henuz git'e eklenmemis)\n{st}"
        diff = subprocess.run(
            "git diff -- " + shlex.quote(path),
            shell=True, cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        return diff.stdout[:3000] or "(diff bos)"
    except subprocess.TimeoutExpired:
        return "(git diff zaman asimina ugradi)"

# NOT: Tum tool fonksiyonlari (read_file, search_code, write_file, replace_text,
# run_command) v0.3.0 R2'de tools/*.py'ye tasindi; R3'te dispatch registry'ye
# baglandi. Bu dosyada sadece paylasilan yardimcilar (_safe_path, _auto_git_diff,
# WORKSPACE, _protocol, BLOCKED_COMMANDS) kaldi; tool modulleri bunlari import eder.


# SYSTEM_PROMPT'un "Kullanabilecegin araclar:" bolumu artik registry'den uretilir.
# ONEMLI: load_tools() prompt kurulmadan ONCE cagrilmali; yoksa registry bos olur ve
# tool listesi bos uretilir. (Tool modulleri _safe_path/_auto_git_diff'i import ettigi
# icin bu cagri o yardimcilar tanimlandiktan SONRA, burada yapilir.)
load_tools()
_tool_list = render_tool_list(registry)

SYSTEM_PROMPT = f"""Sen bir kod asistani agent'isin. Bir gorevi adim adim,
araclar kullanarak cozersin.

Calisma dizinin: {WORKSPACE}

Kullanabilecegin araclar:
{_tool_list}
- final(answer): gorev bitince son cevabini verirsin.

NOT: Dosya degistiren araclar (write_file, replace_text) basarili olunca,
framework OTOMATIK olarak 'git diff' calistirip sonuca ekler. Yani degisikligi
gormek icin ayrica git diff cagirmana gerek yok; sonucta gelen diff'i incele.

IS AKISI: search_code -> read_file -> (write_file|replace_text) -> [otomatik diff]
          -> test -> final. Once anla, sonra degistir, sonra dogrula.

ZORUNLU KURALLAR:
1. Her adimda SADECE tek bir JSON nesnesi dondur, baska HICBIR metin yazma.
2. JSON formati: {{"thought": "...", "tool": "arac_adi", "args": {{...}}}}
3. Degisiklikten sonra gelen otomatik diff'i incele; yanlissa duzelt.
4. Test gerekiyorsa run_command ile calistir; ciktiyi GECTI/KALDI diye degerlendir.
5. Gorev bitince tool olarak "final" kullan, cevabini "answer"a yaz.
6. Yollar calisma dizinine gore goreceli olmali (orn: "agents/main.py").

Ornek:
{{"thought": "Once ilgili kodu bulmaliyim", "tool": "search_code", "args": {{"query": "def main"}}}}
"""


def parse_action(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Modelin ciktisinda JSON bulunamadi.")
    return json.loads(text[start:end + 1])


def run_agent(task, max_steps=12, approver=None, model_config=None):
    load_tools()  # registry'yi doldur (idempotent; importlib modulleri cache'ler)
    approver = approver or TerminalApprover()
    model_config = model_config or default_config()  # env'i cagri aninda oku
    # ctx artik handler yolunun tum calisma-zamani bagimliliklarini tasir:
    #   cwd      -> path kilidi (_safe_path) + git diff koku
    #   approver -> write/replace onayi (import-time global _protocol yerine)
    #   session  -> checkpoint (snapshot/rollback); yoksa duz yazma
    #   git_diff -> degisiklik sonrasi otomatik diff (cwd'ye bagli)
    ctx = SimpleNamespace(
        cwd=WORKSPACE,
        approver=approver,
        session=session,
        git_diff=lambda path: _auto_git_diff(path, WORKSPACE),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Gorev: {task}"},
    ]
    append_event(session, {"type": "user", "content": task})  # gorev basi (step 0)
    for step in range(1, max_steps + 1):
        session.step = step  # transcript step'i anlamli olsun
        print(f"\n=== Adim {step} ===")
        raw = ask_model(messages, model_config)
        messages.append({"role": "assistant", "content": raw})
        append_event(session, {"type": "assistant", "content": raw})
        try:
            action = parse_action(raw)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  (JSON ayristirilamadi: {e})")
            messages.append({"role": "user", "content":
                "Ciktin gecerli bir JSON degildi. Lutfen SADECE istenen "
                "formatta tek bir JSON nesnesi dondur."})
            continue
        thought = action.get("thought", "")
        tool = action.get("tool", "")
        args = action.get("args", {})
        print(f"  dusunce: {thought}")
        print(f"  arac: {tool}  args: {str(args)[:200]}")
        if tool == "final":
            print(f"\n>>> SONUC:\n{args.get('answer', '(bos)')}")
            return
        # Registry dispatch: bilinmeyen tool + handler hatalari iceride
        # ToolObservation'a donusuyor; agent SADECE observation.content gorur.
        obs = registry.dispatch(tool, args, ctx)
        result = obs.content
        append_event(session, {"type": "observation", "tool": tool,
                               "ok": obs.ok, "content": result})
        print(f"  sonuc (ilk 300 krk): {str(result)[:300]}")
        messages.append({"role": "user", "content": f"Aracin sonucu:\n{result}"})
    print("\n>>> Maksimum adim sayisina ulasildi.")


def main():
    parser = argparse.ArgumentParser(description="QuantumLabs kod agent'i (v4)")
    parser.add_argument("--task", help="Agent'a verilecek gorev.")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    print(f"Model: {default_config().model} | Calisma dizini: {WORKSPACE}")
    task = args.task or input("Gorev nedir? ").strip()
    if not task:
        print("Gorev bos, cikiliyor.")
        return
    run_agent(task, max_steps=args.max_steps)


if __name__ == "__main__":
    main()
