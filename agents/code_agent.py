"""QuantumLabs — Kod Agent'i (v4): degisiklik sonrasi OTOMATIK git diff (kodla zorlanir)."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

# code_agent.py agents/ altinda; protocols/ repo kokunde. Repo kokunu sys.path'e ekle.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import ask_model, default_config, get_client  # noqa: F401 (get_client: lazy-guard testleri)
from protocols.safety import TerminalApprover
from runtime.memory_ingest import ingest_session
from runtime.memory_inject import build_memory_context
from runtime.profile import build_user_profile
from runtime.session import Session
from runtime.transcript import append_event
from tools import load_tools, registry
from tools.prompt import render_tool_list

# Model/endpoint konfigurasyonu + client + ask_model artik agents/llm.py'de
# (ortak LLM katmani). code_agent varsayilan olarak DEFAULT_CONFIG kullanir;
# run_agent'a model_config vererek override edilebilir.


# WORKSPACE: fallback calisma dizini (CLI ayni dizinde calisir). Her run_agent
# cagrisi kendi Session'ini/workspace'ini alabilir; global tekil session YOK
# (S1a: "tum cagrilar tek session'a yigilir" kusuru giderildi).
WORKSPACE = os.path.abspath(os.getcwd())

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
5. Bir aracin sonucu sorunun cevabini iceriyorsa DUZ METIN YAZMA; DERHAL "final"
   araci ile bitir ve cevabi "answer"a koy (cevabi thought icine yazma).
6. Ayni araci ayni argumanlarla TEKRAR cagirma; sonuc degismiyorsa "final" ver.
7. Bir islem REDDEDILDI ise aynisini TEKRAR DENEME; farkli yaklas ya da "final" ver.
8. Yollar calisma dizinine gore goreceli olmali (orn: "agents/main.py").
9. DIL: 'final' cevabini KULLANICININ gorevi yazdigi DILDE ver. Kullanici Ingilizce
   yazdiysa Ingilizce, Turkce yazdiysa Turkce, baska bir dilde yazdiysa o dilde
   cevapla. Bir dile ONCEDEN ZORLAMA; kullanicinin dilini yanki gibi izle. (Bu
   sistem talimatinin Turkce olmasi cevabin dilini BELIRLEMEZ.)
10. SOHBET: Selamlasma, tesekkur ya da arac GEREKTIRMEYEN genel bir mesaj gelirse
   arac cagirma; DOGRUDAN 'final' ile yanit ver. Sicak, kisa ve YARDIMSEVER ol:
   selamla, sonra somut olarak nasil yardimci olabilecegini 2-3 ornekle sun (orn.
   kod okuma/arama, dosya duzenleme, test calistirma). Robotik tek cumlelik cevap
   verme; 'answer' alanina dogrudan kullaniciya HITAP eden metni yaz (dusunceyi degil).

Ornekler (yalnizca FORMAT ornegidir; cevap DILI kullaniciya gore degisir):
{{"thought": "Once ilgili kodu bulmaliyim", "tool": "search_code", "args": {{"query": "def main"}}}}
{{"thought": "User asked in English -> answer in English", "tool": "final", "args": {{"answer": "The first line of the README is: # Quantum Labs"}}}}
"""


def parse_action(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Modelin ciktisinda JSON bulunamadi.")
    return json.loads(text[start:end + 1])


def _is_rejection(content):
    """Bir observation'in onay reddi olup olmadigini kabaca anlar.

    edit reddi: 'REDDEDILDI: ...'  |  run_command reddi: 'Kullanici ... reddetti (...)'."""
    low = str(content).strip().lower()
    return low.startswith("redded") or "reddet" in low


def _strip_think(text):
    """Reasoning-model <think>…</think> bloklarini (kapali VE ac-kalmis) temizle.
    Qwen3 gibi modeller cevabi dusunceyle sarar; dusunce ic izdir, cevap DEGIL."""
    text = re.sub(r"<think>.*?</think>", "", str(text), flags=re.S)
    text = re.sub(r"<think>.*$", "", text, flags=re.S)   # kapanmamis <think> -> sonuna kadar at
    return text.strip()


def run_agent(task, max_steps=12, approver=None, model_config=None,
              memory_injection=True, session=None, workspace=None, history=None,
              profile_injection=True):
    """Bir gorevi ReAct dongusuyle cozer.

    Her cagri kendi Session'ini/workspace'ini alir (verilmezse yeni Session +
    WORKSPACE fallback) -> cagrilar birbirinin transcript'ine/checkpoint'ine
    karismaz. Donus: Optional[str] — final cevap; max-step'e ulasilirsa None.

    history: onceki turlarin mesaj tape'i ([{role, content}, ...]). Verilirse
    system ile yeni user mesaji ARASINA konur -> ayni session'da follow-up: agent
    ne yaptigini hatirlar. None (default) -> tek-atis, birinci tur davranisi aynen."""
    load_tools()  # registry'yi doldur (idempotent; importlib modulleri cache'ler)
    workspace = workspace or WORKSPACE          # global sabit fallback (CLI)
    approver = approver or TerminalApprover()
    session = session or Session(workspace)     # HER CAGRIDA YENI (verilmezse)
    # Model secim sirasi: acik param > Session.model_config > env default.
    model_config = (model_config
                    or getattr(session, "model_config", None)
                    or default_config())
    # ctx handler yolunun tum calisma-zamani bagimliliklarini tasir:
    #   cwd      -> path kilidi (_safe_path) + git diff koku
    #   approver -> write/replace onayi
    #   session  -> checkpoint (snapshot/rollback); yoksa duz yazma
    #   git_diff -> degisiklik sonrasi otomatik diff (cwd'ye bagli)
    ctx = SimpleNamespace(
        cwd=workspace,
        approver=approver,
        session=session,
        git_diff=lambda path: _auto_git_diff(path, workspace),
    )
    # Otomatik context enjeksiyonu (task-start): ilgili gecmis kayitlar MODELE
    # giden ilk mesaja eklenir. Best-effort — hata/deps-yok -> block None, agent
    # etkilenmez. YANKI ONLEME: transcript'e ORIJINAL task yazilir; enjekte blok
    # event'e ASLA girmez (yoksa sonraki ingest bloku embed eder -> hafiza yankisi).
    user_content = f"Gorev: {task}"
    if memory_injection:
        try:
            block = build_memory_context(workspace, task)
        except Exception:  # noqa: BLE001 — enjeksiyon asla agent'i dusurmez
            block = None
        if block:
            user_content = f"{block}\n\n{user_content}"

    # Kullanici profili (kalici, kisiye-ozel): system mesajina eklenir (guvenilir).
    # Memory blogu (karantinali, gorev-benzeri gecmis) user mesajina; profil ise
    # DAIMA orada -> selamlasma/sohbet kisisellesir. Best-effort: yoksa None.
    system_content = SYSTEM_PROMPT
    if profile_injection:
        try:
            profile_block = build_user_profile(workspace)
        except Exception:  # noqa: BLE001 — profil asla agent'i dusurmez
            profile_block = None
        if profile_block:
            system_content = f"{SYSTEM_PROMPT}\n\n{profile_block}"

    messages = [{"role": "system", "content": system_content}]
    if history:
        # Follow-up: onceki turlarin tape'i system'den SONRA, yeni user'dan ONCE.
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    append_event(session, {"type": "user", "content": task})  # gorev basi (step 0) — ORIJINAL task
    # (d) Ardisik-tekrar guard durumu: son (tool,args) + son observation.
    prev_key = None
    prev_result = None
    repeat = 1
    try:
        for step in range(1, max_steps + 1):
            session.step = step  # transcript step'i anlamli olsun
            print(f"\n=== Adim {step} ===")
            raw = ask_model(messages, model_config)
            messages.append({"role": "assistant", "content": raw})
            append_event(session, {"type": "assistant", "content": raw})
            try:
                action = parse_action(raw)
            except (ValueError, json.JSONDecodeError):
                # (a) Duz-metin toleransi: JSON action yoksa modelin ciktisini FINAL
                # kabul et. AMA once <think> temizle: reasoning model bazen SADECE
                # dusunce uretip cevabi/JSON'u unutuyor -> ham <think>'i "cevap"
                # sanmak 0 puanli bos yanit demek. Dusunce disi gercek prose varsa
                # onu final kabul et; HIC yoksa modeli 'final' vermeye DURT (donguye
                # devam), sessizce bos cevap dondurme.
                prose = _strip_think(raw)
                if prose:
                    print(f"\n>>> SONUC (duz metin, final olarak kabul edildi):\n{prose}")
                    return prose
                print("  [uyari] model sadece <think> uretti, cevap yok -> durtuluyor")
                messages.append({"role": "user", "content": (
                    "Sadece dusunce (<think>) urettin; kullaniciya CEVAP yok. Simdi "
                    "son cevabini SADECE JSON 'final' action'i ile ver: "
                    '{"thought":"...","tool":"final","args":{"answer":"<cevap>"}}')})
                continue
            thought = action.get("thought", "")
            tool = action.get("tool", "")
            args = action.get("args", {})
            print(f"  dusunce: {thought}")
            print(f"  arac: {tool}  args: {str(args)[:200]}")
            if tool == "final":
                answer = args.get("answer", "(bos)")
                print(f"\n>>> SONUC:\n{answer}")
                return answer   # finally (ingest) yine calisir, sonra doner
            # Registry dispatch: bilinmeyen tool + handler hatalari iceride
            # ToolObservation'a donusuyor; agent SADECE observation.content gorur.
            obs = registry.dispatch(tool, args, ctx)
            result = obs.content
            append_event(session, {"type": "observation", "tool": tool,
                                   "ok": obs.ok, "content": result})
            print(f"  sonuc (ilk 300 krk): {str(result)[:300]}")

            # (d) Ayni (tool,args) VE ayni observation 3 kez ustuste -> dongu kilitli:
            # kir ve son observation'i ozetleyen bir final dondur.
            key = (tool, json.dumps(args, sort_keys=True, default=str))
            repeat = repeat + 1 if (key == prev_key and result == prev_result) else 1
            prev_key, prev_result = key, result
            if repeat >= 3:
                summary = (f"[dongu durduruldu] '{tool}' araci ayni argumanlarla 3 kez "
                           f"ardisik AYNI sonucu verdi. Son sonuc:\n{result}")
                print(f"\n>>> SONUC (tekrar guard):\n{summary}")
                return summary

            # (b) Rejection vurgusu: reddedilen action'i modele ACIK uyariyla besle.
            if _is_rejection(result):
                feedback = (f"Aracin sonucu:\n{result}\n\n"
                            "UYARI: Bu islem REDDEDILDI. Ayni action'i TEKRAR DENEME; "
                            "farkli bir yaklasim sec ya da 'final' araciyla durumu acikla.")
            else:
                feedback = f"Aracin sonucu:\n{result}"
            messages.append({"role": "user", "content": feedback})
        print("\n>>> Maksimum adim sayisina ulasildi.")
    finally:
        # Tur bitince (final/max-step/hata) hafizayi guncelle. Best-effort:
        # ingest_session kendi icinde hatayi yutar; deps yoksa 0 doner, agent dusmez.
        n = ingest_session(session.session_id, session.workspace)
        if n:
            print(f"  (hafiza guncellendi: {n} chunk)")
    return None   # max-step'e ulasildi (final gelmedi)


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
