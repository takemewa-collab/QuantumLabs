"""Ollama (qwen3:8b) üzerinde çalışan interaktif sohbet agent'i.

Özellikler:
- Konuşma geçmişi (multi-turn): model önceki mesajları hatırlar.
- Streaming: cevap parça parça, yazılırken ekrana akar.
- Özelleştirilebilir sistem prompt'u (--system veya AGENT_SYSTEM env).

OpenAI uyumlu API kullanır (base_url=http://localhost:11434/v1).

v0.3.2 A3.1: client/config ortak agents.llm katmanindan gelir (get_client).
Streaming döngüsü AYNEN agent'ta kalir; model AÇIKÇA qwen3:8b (hardcode korunur),
temperature bugun gönderilmiyordu -> göndermeye devam ETMEZ.

Kullanım:
    python agents/chat_agent.py
    python agents/chat_agent.py --system "Sen bir Python uzmanısın."

Komutlar (sohbet içinde):
    /reset  -> geçmişi temizler
    /quit   -> çıkar (veya Ctrl-D / Ctrl-C)
"""

import argparse
import os
import sys
from dataclasses import replace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import default_config, get_client

DEFAULT_SYSTEM = "Sen yardımcı bir asistansın. Kısa ve net cevap ver."


def stream_answer(messages, cfg):
    """Mesaj geçmişini modele gönderir, cevabı akıtarak yazdırır ve metni döndürür."""
    stream = get_client(cfg).chat.completions.create(
        model=cfg.model,
        messages=messages,
        stream=True,
    )
    chunks = []
    for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            chunks.append(delta)
    print()
    return "".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ollama qwen3:8b sohbet agent'i")
    parser.add_argument(
        "--system",
        default=os.environ.get("AGENT_SYSTEM", DEFAULT_SYSTEM),
        help="Sistem prompt'u (modelin rolü/davranışı).",
    )
    args = parser.parse_args()

    # Model AÇIKÇA qwen3:8b; temperature=None -> istekte gönderilmez (eski davranis).
    cfg = replace(default_config(), model="qwen3:8b", temperature=None)

    messages = [{"role": "system", "content": args.system}]

    print(f"Model: {cfg.model} | Sistem: {args.system}")
    print("Komutlar: /reset (geçmişi sil), /quit (çık)\n")

    while True:
        try:
            question = input("Soru: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGörüşürüz!")
            break

        if not question:
            continue
        if question == "/quit":
            print("Görüşürüz!")
            break
        if question == "/reset":
            messages = [{"role": "system", "content": args.system}]
            print("(geçmiş temizlendi)\n")
            continue

        messages.append({"role": "user", "content": question})
        print("\nCevap: ", end="", flush=True)
        answer = stream_answer(messages, cfg)
        messages.append({"role": "assistant", "content": answer})
        print()


if __name__ == "__main__":
    main()
