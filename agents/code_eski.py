"""Ollama (deepseek-coder:6.7b) üzerinde çalışan kod-yazan bir agent.

OpenAI uyumlu API kullanır (base_url=http://localhost:11434/v1).

Akış:
    1. Kullanıcı bir istek yazar.
    2. Model kod üretir.
    3. Agent yanıttan ```python ... ``` bloğunu ayıklar.
    4. Kodu workspace/ klasörüne .py olarak kaydeder.
    5. "çalıştırayım mı?" diye sorar; "e" ise subprocess ile çalıştırır.

Güvenlik: kod yalnızca workspace/ klasörüne yazılır ve oradan çalıştırılır.
Döngü "/quit" yazılınca biter.
"""

import os
import re
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from typing import Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import ask_model, default_config  # v0.3.2 A3.2: ortak LLM katmani

# Bu dosyanın yanındaki workspace/ klasörü (agents/workspace).
WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")

SYSTEM_PROMPT = (
    "Sen uzman bir Python geliştiricisisin. Kullanıcının isteğine göre temiz, "
    "çalışır Python kodu üret. Kodu tek bir ```python ... ``` bloğu içinde ver. "
    "Açıklamaları kısa tut."
)

# ```python ... ``` bloğunu yakalayan desen (DOTALL ile çok satırlı eşleşme).
CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def generate_code(prompt: str) -> str:
    """İsteği modele gönderir ve modelin ham yanıtını döndürür."""
    # Model AÇIKÇA deepseek-coder:6.7b (hardcode korunur); temperature=None ->
    # istekte gönderilmez (eski davranis: server default).
    cfg = replace(default_config(), model="deepseek-coder:6.7b", temperature=None)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return ask_model(messages, cfg)


def extract_code(text: str) -> Optional[str]:
    """Yanıttan ilk ```python ... ``` bloğunu ayıklar.

    Blok bulunamazsa None döner.
    """
    match = CODE_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


def save_code(code: str) -> str:
    """Kodu workspace/ içine zaman damgalı bir .py dosyası olarak kaydeder.

    Kaydedilen dosyanın tam yolunu döndürür. Yazma yalnızca workspace/
    klasörüne yapılır (güvenlik kısıtı).
    """
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    filename = "snippet_{0}.py".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    filepath = os.path.join(WORKSPACE_DIR, filename)

    # Güvenlik: çözümlenen yolun workspace/ içinde kaldığından emin ol.
    if os.path.commonpath([os.path.abspath(filepath), WORKSPACE_DIR]) != WORKSPACE_DIR:
        raise ValueError("Güvenlik hatası: dosya workspace/ dışına yazılamaz.")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    return filepath


def run_code(filepath: str) -> None:
    """Kaydedilen .py dosyasını subprocess ile çalıştırır.

    stdout ve stderr çıktısını ekrana basar. Çalıştırma yalnızca workspace/
    klasöründeki dosyalar için yapılır.
    """
    if os.path.commonpath([os.path.abspath(filepath), WORKSPACE_DIR]) != WORKSPACE_DIR:
        print("Güvenlik hatası: yalnızca workspace/ içindeki kodlar çalıştırılır.")
        return

    print("\n--- Çalıştırılıyor ---")
    try:
        result = subprocess.run(
            [sys.executable, filepath],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=WORKSPACE_DIR,
        )
    except subprocess.TimeoutExpired:
        print("Hata: kod 30 saniye içinde tamamlanmadı (zaman aşımı).")
        return
    except OSError as exc:
        print("Hata: kod çalıştırılamadı -> {0}".format(exc))
        return

    if result.stdout:
        print("[stdout]")
        print(result.stdout)
    if result.stderr:
        print("[stderr]")
        print(result.stderr)
    print("--- Bitti (çıkış kodu: {0}) ---".format(result.returncode))


def handle_request(prompt: str) -> None:
    """Tek bir kullanıcı isteğini baştan sona işler."""
    # 1) Modelden kod iste (bağlantı hataları burada yakalanır).
    try:
        raw_response = generate_code(prompt)
    except Exception as exc:  # openai bağlantı/istek hataları
        print(
            "Hata: modele bağlanılamadı. Ollama çalışıyor mu? "
            "(ollama serve ve `ollama pull deepseek-coder:6.7b`)\n"
            "Ayrıntı: {0}".format(exc)
        )
        return

    # 2) Yanıttan kod bloğunu ayıkla.
    code = extract_code(raw_response)
    if code is None:
        print("Hata: yanıtta ```python``` kod bloğu bulunamadı. Model yanıtı:\n")
        print(raw_response)
        return

    # 3) Kodu kaydet.
    try:
        filepath = save_code(code)
    except (OSError, ValueError) as exc:
        print("Hata: kod kaydedilemedi -> {0}".format(exc))
        return

    print("\nÜretilen kod:\n")
    print(code)
    print("\nKaydedildi: {0}".format(filepath))

    # 4) Çalıştırmak isteyip istemediğini sor.
    answer = input("\nÇalıştırayım mı? (e/h): ").strip().lower()
    if answer == "e":
        run_code(filepath)
    else:
        print("Çalıştırılmadı.")


def main() -> None:
    print("Kod Agent'ı (deepseek-coder:6.7b). Çıkmak için /quit yazın.\n")
    while True:
        try:
            prompt = input("İstek: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGörüşürüz!")
            break

        if not prompt:
            continue
        if prompt == "/quit":
            print("Görüşürüz!")
            break

        handle_request(prompt)
        print()  # döngüler arasında boşluk


if __name__ == "__main__":
    main()
