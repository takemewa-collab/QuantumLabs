"""Ollama (qwen3:8b) üzerinde çalışan basit bir agent.

OpenAI uyumlu API kullanır (base_url=http://localhost:11434/v1).
Bir soru alır, modele gönderir ve cevabı yazdırır.

v0.3.2 A3.1: LLM erisimi ortak agents.llm katmanina tasindi. Model AÇIKÇA
qwen3:8b (bugunku hardcode korunur); temperature=None -> istekte gonderilmez
(eski davranis: server default).
"""

import os
import sys
from dataclasses import replace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.llm import ask_model, default_config


def ask(question: str) -> str:
    """Soruyu modele gönderir ve cevabı döndürür."""
    cfg = replace(default_config(), model="qwen3:8b", temperature=None)
    messages = [
        {"role": "system", "content": "Sen yardımcı bir asistansın."},
        {"role": "user", "content": question},
    ]
    return ask_model(messages, cfg)


def main() -> None:
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("Soru: ")

    print("\nCevap:\n")
    print(ask(question))


if __name__ == "__main__":
    main()
