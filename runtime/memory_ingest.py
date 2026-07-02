"""QuantumLabs — Memory ingest (v0.4.0 B3a): transcript jsonl -> embed -> chroma.

search_memory tool'u YOK (B3b). Bu katman jsonl transcript'leri sorgulanabilir
bir vektor index'e donusturur.

TASARIM — HER SEY LAZY (A2.0 dersi): sentence_transformers ve chromadb yalnizca
fonksiyon govdesinde import edilir. Boylece `import runtime.memory_ingest` (ve
onu import eden agents.code_agent) yan-etkisiz ve HIZLI kalir; agar (~7s) embed
soguk-start'i sadece gercek ingest aninda odenir.

Yol: <workspace>/.quantumlabs/memory/  (chroma PersistentClient)
Koleksiyon: "transcript_turns" (cosine)
ID: f"{session_id}:{step}"  -> deterministik; tekrar ingest duplicate yaratmaz.

Best-effort: ingest hatasi (deps yok, disk vb.) agent'i ASLA dusurmez; stderr'e
uyari + 0 doner (runtime/transcript.py deseniyle ayni).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache

_MEMORY_SUBDIR = os.path.join(".quantumlabs", "memory")
_TRANSCRIPT_SUBDIR = os.path.join(".quantumlabs", "transcripts")
# Cok-dilli embedder (Turkce transcript'ler icin L6-en'den belirgin daha iyi).
# Ileride config'e tasinabilir.
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
# Koleksiyon adina model kisaltmasi: farkli vektor uzayi eski L6 vektorleriyle
# KARISAMASIN (eski "transcript_turns" varsa dursun, bu ayri).
_COLLECTION = "transcript_turns_ml12"


@dataclass
class Turn:
    """Embed birimi. text = chroma document (ham content'ler); embed_text =
    embedding icin temizlenmis (assistant JSON action'i -> yalniz 'thought')."""
    text: str
    embed_text: str
    metadata: dict


@lru_cache(maxsize=1)
def _get_embedder():
    """Cok-dilli MiniLM (384-dim), tek instance. Import FONKSIYON ICINDE (lazy)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def _assistant_embed_text(content: str) -> str:
    """Assistant content JSON action ise embed icin yalniz 'thought'u dondur;
    tool/args gurultusu embedding'i seyreltmesin. Parse edilemezse ham metin."""
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(content[start:end + 1])
        except (ValueError, TypeError):
            obj = None
        if isinstance(obj, dict) and obj.get("thought"):
            return str(obj["thought"])
    return content


@lru_cache(maxsize=None)
def _get_collection(workspace: str):
    """workspace basina tek chroma koleksiyonu. Import FONKSIYON ICINDE (lazy)."""
    import chromadb
    path = os.path.join(workspace, _MEMORY_SUBDIR)
    os.makedirs(path, exist_ok=True)
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(_COLLECTION, metadata={"hnsw:space": "cosine"})


def _read_events(jsonl_path: str) -> list:
    events = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _build_turn(events: list) -> Turn:
    doc_parts, embed_parts = [], []
    for e in events:
        content = e.get("content")
        if not content:
            continue
        doc_parts.append(content)                      # document: ham content
        if e.get("type") == "assistant":
            embed_parts.append(_assistant_embed_text(content))   # temiz: sadece thought
        else:
            embed_parts.append(content)
    text = "\n".join(doc_parts)
    embed_text = "\n".join(p for p in embed_parts if p)
    first = events[0]
    step = first.get("step")
    return Turn(
        text=text,
        embed_text=embed_text,
        metadata={
            # chroma metadata: sadece str/int/float/bool (None/list KABUL ETMEZ)
            "session_id": first.get("session_id") or "",
            "step": step if isinstance(step, int) else -1,
            "ts": first.get("ts") or "",
            "event_types": ",".join(e.get("type", "") for e in events),
        },
    )


def chunk_turns(jsonl_path: str) -> list:
    """Event'leri TUR-bazinda grupla: bir tur = assistant + onu izleyen
    observation(lar); user event (step 0) tek basina bir chunk."""
    events = _read_events(jsonl_path)
    groups = []          # list[list[event]]
    cur = None
    for ev in events:
        etype = ev.get("type")
        if etype == "user":
            if cur:
                groups.append(cur)
                cur = None
            groups.append([ev])              # user tek basina
        elif etype == "assistant":
            if cur:
                groups.append(cur)
            cur = [ev]                        # yeni tur assistant ile baslar
        elif etype == "observation":
            if cur is None:
                cur = [ev]
            else:
                cur.append(ev)
    if cur:
        groups.append(cur)
    return [_build_turn(g) for g in groups if any(e.get("content") for e in g)]


def ingest_session(session_id: str, workspace: str) -> int:
    """Bir oturumun transcript'ini chunk'la, embed et (batch), chroma'ya upsert.

    Deterministik ID (session_id:step) -> tekrar ingest gunceller, duplicate yok.
    Donus: upsert edilen chunk sayisi. Dosya yoksa 0. Hata sizmaz (best-effort)."""
    try:
        jsonl = os.path.join(workspace, _TRANSCRIPT_SUBDIR, f"{session_id}.jsonl")
        if not os.path.exists(jsonl):
            return 0
        turns = chunk_turns(jsonl)
        if not turns:
            return 0
        # Embedding TEMIZ metinden (assistant JSON gurultusu haric); chroma
        # document ise ham tur metni (retrieval snippet'i tam kalsin).
        embeddings = _get_embedder().encode([t.embed_text for t in turns]).tolist()
        ids = [f"{session_id}:{t.metadata['step']}" for t in turns]
        _get_collection(workspace).upsert(
            ids=ids,
            embeddings=embeddings,
            documents=[t.text for t in turns],
            metadatas=[t.metadata for t in turns],
        )
        return len(turns)
    except Exception as e:  # noqa: BLE001 — best-effort; agent'i asla dusurme
        print(f"[memory_ingest] ingest hatasi (yok sayildi): {e}", file=sys.stderr)
        return 0


def ingest_all(workspace: str) -> dict:
    """transcripts/ altindaki tum jsonl'ler icin ingest_session. {session_id: n}."""
    result = {}
    tdir = os.path.join(workspace, _TRANSCRIPT_SUBDIR)
    if not os.path.isdir(tdir):
        return result
    for name in sorted(os.listdir(tdir)):
        if name.endswith(".jsonl"):
            session_id = name[: -len(".jsonl")]
            result[session_id] = ingest_session(session_id, workspace)
    return result


def _main() -> None:
    workspace = os.path.abspath(os.getcwd())
    result = ingest_all(workspace)
    total = sum(result.values())
    print(f"ingest_all: {len(result)} oturum, {total} chunk -> "
          f"{os.path.join(workspace, _MEMORY_SUBDIR)}")
    for session_id, n in result.items():
        print(f"  {session_id}: {n} chunk")


if __name__ == "__main__":
    _main()
