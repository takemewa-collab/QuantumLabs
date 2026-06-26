"""Ollama (qwen3:8b) üzerinde çalışan basit bir agent.

OpenAI uyumlu API kullanır (base_url=http://localhost:11434/v1).
Bir soru alır, modele gönderir ve cevabı yazdırır.
"""

import sys

from openai import OpenAI

BASE_URL = "http://localhost:11434/v1"
API_KEY = "ollama"  # Ollama herhangi bir anahtarı kabul eder
MODEL = "qwen3:8b"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def ask(question: str) -> str:
    """Soruyu modele gönderir ve cevabı döndürür."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Sen yardımcı bir asistansın."},
            {"role": "user", "content": question},
        ],
    )
    return response.choices[0].message.content


def main() -> None:
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("Soru: ")

    print("\nCevap:\n")
    print(ask(question))


if __name__ == "__main__":
    main()
