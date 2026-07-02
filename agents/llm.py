"""QuantumLabs — Ortak LLM katmani (v0.3.2 A3.0).

Model/endpoint konfigurasyonu + lazy client + ask_model tek yerde toplanir.
Simdilik yalnizca code_agent kullanir; chat_agent / simple_agent / code_eski
A3.1/A3.2'de bu katmana gecirilecek.

Env override (kod degistirmeden): QL_BASE_URL / QL_API_KEY / QL_MODEL.
Py3.9 uyumlu (Optional[...] kullanilir, X | Y degil).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from openai import OpenAI


@dataclass(frozen=True)
class ModelConfig:
    """LLM cagrisinin tum ayari; frozen -> hashable -> lru_cache anahtari olabilir."""
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2


def default_config() -> ModelConfig:
    """Env'i CAGRI ANINDA okur (import-time donma yok).

    Override (kod degistirmeden): QL_BASE_URL / QL_API_KEY / QL_MODEL. Boylece
    import'tan SONRA env degistirmek de etkili olur."""
    return ModelConfig(
        base_url=os.getenv("QL_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("QL_API_KEY", "ollama"),
        model=os.getenv("QL_MODEL", "deepseek-coder-v2:16b"),
    )


@lru_cache(maxsize=None)
def get_client(cfg: ModelConfig) -> OpenAI:
    """cfg basina tek OpenAI/Ollama client (lazy; import-time yan-etki yok).

    frozen ModelConfig cache anahtaridir; ayni cfg tekrar client kurmaz."""
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def ask_model(messages, cfg: Optional[ModelConfig] = None) -> str:
    cfg = cfg or default_config()
    resp = get_client(cfg).chat.completions.create(
        model=cfg.model, messages=messages, temperature=cfg.temperature,
    )
    return resp.choices[0].message.content
