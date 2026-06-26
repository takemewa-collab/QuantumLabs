"""Ollama (qwen3:8b) üzerinde çalışan interaktif sohbet agent'i.

Özellikler:
- Konuşma geçmişi (multi-turn): model önceki mesajları hatırlar.
- Streaming: cevap parça parça, yazılırken ekrana akar.
- Özelleştirilebilir sistem prompt'u (--system veya AGENT_SYSTEM env).

OpenAI uyumlu API kullanır (base_url=http://localhost:11434/v1).

Kullanım:
    python agents/chat_agent.py
    python agents/chat_agent.py --system "Sen bir Python uzmanısın."

Komutlar (sohbet içinde):
    /reset  -> geçmişi temizler
    /quit   -> çıkar (veya Ctrl-D / Ctrl-C)
"""

import argparse
import os

from openai import OpenAI

BASE_URL = "http://localhost:11434/v1"
API_KEY = "ollama"  # Ollama herhangi bir anahtarı kabul eder
MODEL = "qwen3:8b"
DEFAULT_SYSTEM = "Sen yardımcı bir asistansın. Kısa ve net cevap ver."

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def stream_answer(messages):
    """Mesaj geçmişini modele gönderir, cevabı akıtarak yazdırır ve metni döndürür."""
    stream = client.chat.completions.create(
        model=MODEL,
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

    messages = [{"role": "system", "content": args.system}]

    print(f"Model: {MODEL} | Sistem: {args.system}")
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
        answer = stream_answer(messages)
        messages.append({"role": "assistant", "content": answer})
        print()


if __name__ == "__main__":
    main()
