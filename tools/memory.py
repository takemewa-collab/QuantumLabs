"""QuantumLabs — Hafiza arama araci (v0.4.0 B3b): search_memory.

Agent kendi gecmis oturum transcript'lerinde (B3a'da ingest edilmis) anlamsal
arama yapar. Kod DEGIL; kod aramak icin search_code. Embedder/collection
runtime.memory_ingest'ten LAZY alinir (tek kaynak) — bu modulun import'u
yan-etkisiz kalir (sentence_transformers/chromadb yuklenmez).
"""
from __future__ import annotations

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

    # Sorgu mantigi tek yerde (runtime.memory_ingest.query_memory); formatlama burada.
    # query_memory LAZY: memory dizini yoksa/bos ise chroma yuklenmeden [] doner.
    from runtime.memory_ingest import query_memory
    results = query_memory(ctx.cwd, query, top_k)
    if not results:
        return "hafizada kayit yok veya eslesme bulunamadi."

    lines = []
    for r in results:
        sid = r["session_id"]
        sid_short = sid[-8:] if len(sid) > 8 else sid    # kisa oturum-id
        date = (r["ts"] or "")[:10]                       # YYYY-MM-DD
        snippet = r["text"].replace("\n", " ")[:200]
        lines.append(f"[{r['score']}] (oturum {sid_short}, adim {r['step']}, {date}) {snippet}")
    return "\n".join(lines)
