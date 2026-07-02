"""QuantumLabs — Hafiza arama araci (v0.4.0 B3b): search_memory.

Agent kendi gecmis oturum transcript'lerinde (B3a'da ingest edilmis) anlamsal
arama yapar. Kod DEGIL; kod aramak icin search_code. Embedder/collection
runtime.memory_ingest'ten LAZY alinir (tek kaynak) — bu modulun import'u
yan-etkisiz kalir (sentence_transformers/chromadb yuklenmez).
"""
from __future__ import annotations

import os

from tools.registry import ToolParam, registry


@registry.tool(
    name="search_memory",
    description=("Gecmis oturum hafizasinda anlamsal arama yapar (transcript "
                 "arsivi). Kod DEGIL gecmis konusma/karar aramak icin kullan; "
                 "kod aramak icin search_code."),
    params=(
        ToolParam(name="query", type="string", description="aranacak ifade"),
        ToolParam(name="top_k", type="integer",
                  description="kac sonuc (varsayilan 3)", required=False),
    ),
)
def search_memory(args: dict, ctx) -> str:
    query = args["query"]
    try:
        top_k = int(args.get("top_k", 3))
    except (TypeError, ValueError):
        top_k = 3

    # Ucuz on-kontrol: memory dizini yoksa chroma'yi hic yukleme (bos hafiza normal).
    from runtime.memory_ingest import _MEMORY_SUBDIR
    if not os.path.isdir(os.path.join(ctx.cwd, _MEMORY_SUBDIR)):
        return "hafizada kayit yok (henuz transcript ingest edilmemis)."

    try:
        from runtime.memory_ingest import _get_collection, _get_embedder
        collection = _get_collection(ctx.cwd)
        if collection.count() == 0:
            return "hafizada kayit yok (henuz transcript ingest edilmemis)."
        query_emb = _get_embedder().encode([query]).tolist()
        res = collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:  # kullanici-dostu; runner zaten sarar ama mesaj net olsun
        return f"HATA: hafiza aramasi basarisiz: {e}"

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    if not docs:
        return f"'{query}' icin hafizada eslesme bulunamadi."

    lines = []
    for doc, meta, dist in zip(docs, metas, dists):
        score = round(1 - dist, 2)                       # cosine benzerlik ~ 1-distance
        sid = meta.get("session_id") or "?"
        sid_short = sid[-8:] if len(sid) > 8 else sid    # kisa oturum-id
        step = meta.get("step", "?")
        date = (meta.get("ts") or "")[:10]               # YYYY-MM-DD
        snippet = doc.replace("\n", " ")[:200]
        lines.append(f"[{score}] (oturum {sid_short}, adim {step}, {date}) {snippet}")
    return "\n".join(lines)
