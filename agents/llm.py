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
    temperature: Optional[float] = 0.2   # None -> istekte hic gonderilmez (server default)


def default_config() -> ModelConfig:
    """Env'i CAGRI ANINDA okur (import-time donma yok).

    Override (kod degistirmeden): QL_BASE_URL / QL_API_KEY / QL_MODEL. Boylece
    import'tan SONRA env degistirmek de etkili olur."""
    return ModelConfig(
        base_url=os.getenv("QL_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("QL_API_KEY", "ollama"),
        model=os.getenv("QL_MODEL", "deepseek-coder-v2:16b"),
    )


def quantum_pod_config() -> ModelConfig:
    """QUANTUM_POD: uzak OpenAI-uyumlu endpoint config'i (env-override'li).

    default_config gibi env'i CAGRI ANINDA okur -> Session'a iliştirmek icin
    veya run_agent(model_config=quantum_pod_config()) ile kullanilabilir."""
    return ModelConfig(
        base_url=os.getenv("QUANTUM_POD_BASE_URL", "https://pod.quantumlabs.internal/v1"),
        api_key=os.getenv("QUANTUM_POD_API_KEY", "quantum"),
        model=os.getenv("QUANTUM_POD_MODEL", "deepseek-coder-v2:16b"),
    )


# İsimli sabit (import anindaki env ile) — kolay kullanim icin:
#   Session(ws, model_config=QUANTUM_POD)
# Env'i cagri aninda okumak istersen quantum_pod_config() cagir.
QUANTUM_POD = quantum_pod_config()


@lru_cache(maxsize=None)
def get_client(cfg: ModelConfig) -> OpenAI:
    """cfg basina tek OpenAI/Ollama client (lazy; import-time yan-etki yok).

    frozen ModelConfig cache anahtaridir; ayni cfg tekrar client kurmaz."""
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def ask_model(messages, cfg: Optional[ModelConfig] = None) -> str:
    cfg = cfg or default_config()
    kwargs = dict(model=cfg.model, messages=messages)
    if cfg.temperature is not None:      # None ise gonderme -> server default korunur
        kwargs["temperature"] = cfg.temperature
    resp = get_client(cfg).chat.completions.create(**kwargs)
    return resp.choices[0].message.content
