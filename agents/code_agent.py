"""QuantumLabs — Kod Agent'i (v4): degisiklik sonrasi OTOMATIK git diff (kodla zorlanir)."""

import argparse
import json
import os
import shlex
import subprocess
import sys

from openai import OpenAI

# code_agent.py agents/ altinda; protocols/ repo kokunde. Repo kokunu sys.path'e ekle.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from protocols.safety import SafeEditProtocol, TerminalApprover
from runtime.session import Session

BASE_URL = "http://localhost:11434/v1"
API_KEY = "ollama"
MODEL = "deepseek-coder-v2:16b"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
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

SYSTEM_PROMPT = f"""Sen bir kod asistani agent'isin. Bir gorevi adim adim,
araclar kullanarak cozersin.

Calisma dizinin: {WORKSPACE}

Kullanabilecegin araclar:
- read_file(path): bir dosyanin icerigini okur.
- search_code(query): tum repoda bir metin/kod arar (grep gibi). Repoyu
  anlamanin en hizli yolu budur.
- write_file(path, content): bir dosyaya bastan icerik yazar (uzerine yazar).
- replace_text(path, old, new): bir dosyada 'old' metnini 'new' ile degistirir.
  Kucuk degisiklikler icin write_file yerine BUNU tercih et.
- run_command(command): bir kabuk komutu calistirir (git, pytest, python vb.).
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


def _safe_path(path):
    """Yolu calisma dizinine kilitler (commonpath; startswith guvenilmez)."""
    full = os.path.abspath(os.path.join(WORKSPACE, path))
    if os.path.commonpath([WORKSPACE, full]) != WORKSPACE:
        raise ValueError(f"Guvenlik: calisma dizini disina erisim engellendi: {path}")
    return full


def _auto_git_diff(path):
    """Bir dosya degistikten sonra otomatik calisir. Framework garantisi:
    degisikligi gormek modelin insafina birakilmaz, kodla zorlanir."""
    try:
        status = subprocess.run(
            "git status --short -- " + shlex.quote(path),
            shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=10,
        )
        st = status.stdout.strip()
        if not st:
            if not os.path.isdir(os.path.join(WORKSPACE, ".git")):
                return "(git deposu degil; diff atlandi)"
            return "(degisiklik git tarafindan gorulmedi)"
        if st.startswith("??"):
            return f"(yeni dosya, henuz git'e eklenmemis)\n{st}"
        diff = subprocess.run(
            "git diff -- " + shlex.quote(path),
            shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=10,
        )
        return diff.stdout[:3000] or "(diff bos)"
    except subprocess.TimeoutExpired:
        return "(git diff zaman asimina ugradi)"


def tool_read_file(args):
    path = _safe_path(args["path"])
    if not os.path.exists(path):
        return f"HATA: dosya bulunamadi: {args['path']}"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    if len(content) > 6000:
        content = content[:6000] + "\n... [dosya kirpildi] ..."
    return content


def tool_search_code(args):
    query = args["query"]
    rg = subprocess.run("command -v rg", shell=True, capture_output=True, text=True)
    cmd = (["rg", "-n", "--no-heading", query, WORKSPACE] if rg.stdout.strip()
           else ["grep", "-rn", query, WORKSPACE])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        out = result.stdout.strip().replace(WORKSPACE + "/", "")
        if not out:
            return f"'{query}' icin eslesme bulunamadi."
        return out[:4000] if len(out) <= 4000 else out[:4000] + "\n... [kirpildi] ..."
    except subprocess.TimeoutExpired:
        return "HATA: arama 20 saniyede bitmedi."


def tool_write_file(args):
    outcome = _protocol.write_file(args["path"], args["content"])
    if not outcome.applied:
        return outcome.message
    diff = _auto_git_diff(args["path"])
    return f"{outcome.message}\n\nGIT DIFF:\n{diff}"


def tool_replace_text(args):
    outcome = _protocol.replace_text(args["path"], args["old"], args["new"])
    if not outcome.applied:
        return outcome.message
    diff = _auto_git_diff(args["path"])
    return f"{outcome.message}\n\nGIT DIFF:\n{diff}"


def tool_run_command(args):
    command = args["command"]
    for bad in BLOCKED_COMMANDS:
        if bad in command:
            return f"HATA: tehlikeli komut engellendi ('{bad}' iceriyor)."
    print(f"\n  [!] Agent su komutu calistirmak istiyor:\n      {command}")
    if input("  Onayliyor musun? [e/h]: ").strip().lower() != "e":
        return "Kullanici komut calistirmayi reddetti."
    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKSPACE,
            capture_output=True, text=True, timeout=30,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out.strip()[:4000] or "(komut cikti uretmedi)"
    except subprocess.TimeoutExpired:
        return "HATA: komut 30 saniyede bitmedi (zaman asimi)."


TOOLS = {
    "read_file": tool_read_file,
    "search_code": tool_search_code,
    "write_file": tool_write_file,
    "replace_text": tool_replace_text,
    "run_command": tool_run_command,
}


def parse_action(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Modelin ciktisinda JSON bulunamadi.")
    return json.loads(text[start:end + 1])


def ask_model(messages):
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.2,
    )
    return resp.choices[0].message.content


def run_agent(task, max_steps=12):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Gorev: {task}"},
    ]
    for step in range(1, max_steps + 1):
        print(f"\n=== Adim {step} ===")
        raw = ask_model(messages)
        messages.append({"role": "assistant", "content": raw})
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
        if tool not in TOOLS:
            result = f"HATA: '{tool}' diye bir arac yok. Gecerli: {', '.join(TOOLS)}, final."
        else:
            try:
                result = TOOLS[tool](args)
            except Exception as e:
                result = f"HATA: arac calisirken hata: {e}"
        print(f"  sonuc (ilk 300 krk): {str(result)[:300]}")
        messages.append({"role": "user", "content": f"Aracin sonucu:\n{result}"})
    print("\n>>> Maksimum adim sayisina ulasildi.")


def main():
    parser = argparse.ArgumentParser(description="QuantumLabs kod agent'i (v4)")
    parser.add_argument("--task", help="Agent'a verilecek gorev.")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    print(f"Model: {MODEL} | Calisma dizini: {WORKSPACE}")
    task = args.task or input("Gorev nedir? ").strip()
    if not task:
        print("Gorev bos, cikiliyor.")
        return
    run_agent(task, max_steps=args.max_steps)


if __name__ == "__main__":
    main()
