"""QuantumLabs — ToolRegistry (v0.3.0 R1): tool tanimi + kayit iskeleti.

Bu R1 SADECE iskelet: hicbir tool tasinmaz, dispatch henuz calismaz.
Amac; bugune kadar code_agent.py icindeki if/elif dispatch'e dagilmis
tool bilgisini (isim, aciklama, parametreler, handler) tek bir yerde,
introspection'a acik sekilde toplamak.

    ToolContext   -> handler'a gecen calisma-zamani baglami (Protocol; duck typing)
    ToolParam     -> tek bir parametrenin tarifi (introspection/JSON schema icin)
    Tool          -> bir aracin tam tarifi (isim + aciklama + parametreler + handler)
    ToolRegistry  -> araclari kaydeden/sorgulayan kayit defteri
    registry      -> modul-seviyesi singleton

R2: mevcut tool'lari buraya tasi. R3: dispatch() gercek dispatch yapar.
R4: SYSTEM_PROMPT'u registry'den uret.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Protocol, runtime_checkable

__all__ = [
    "ToolContext", "ToolParam", "Tool", "ToolHandler",
    "ToolRegistry", "registry",
]


@runtime_checkable
class ToolContext(Protocol):
    """Handler'a gecen calisma-zamani baglami.

    Simdilik sadece calisma dizini. Protocol oldugu icin ileride (session,
    approver, workspace koku vs.) alanlar eklenince somut tasiyicilar
    degismeden uyumlu kalir.
    """
    cwd: str


# handler(args, ctx) -> arac ciktisi (genelde str, ama serbest).
ToolHandler = Callable[[Dict[str, Any], ToolContext], Any]


@dataclass(frozen=True)
class ToolParam:
    """Tek bir tool parametresinin tarifi (introspection + ileride JSON schema)."""
    name: str
    type: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class Tool:
    """Bir aracin tam tarifi: kimlik + parametreler + calistiran handler."""
    name: str
    description: str
    params: tuple[ToolParam, ...]
    handler: ToolHandler


class ToolRegistry:
    """Araclari kaydeden ve sorgulayan kayit defteri.

    Kayit iki yoldan yapilir:
      - register(tool): hazir bir Tool nesnesini ekler.
      - @tool(...) decorator: bir fonksiyonu handler olarak sarip kaydeder.
    Ayni isimde ikinci kayit ValueError firlatir (sessiz ustune yazma yok).
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"'{tool.name}' zaten kayitli (duplicate tool).")
        self._tools[tool.name] = tool
        return tool

    def tool(
        self,
        name: str,
        description: str,
        params: tuple[ToolParam, ...] = (),
    ) -> Callable[[ToolHandler], ToolHandler]:
        """Decorator: bir fonksiyonu Tool olarak kaydeder, fonksiyonu geri dondurur."""

        def decorator(handler: ToolHandler) -> ToolHandler:
            self.register(Tool(name=name, description=description,
                               params=tuple(params), handler=handler))
            return handler

        return decorator

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def all(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def dispatch(self, name: str, args: Dict[str, Any], ctx: ToolContext) -> ToolObservation:
        # Kayitli handler'i bul, yoksa temiz bir ok=False gozlemi don; varsa
        # ToolRunner ile guvenli calistir (handler patlarsa dongun dusmez).
        # Lazy import: runner/observation'i modul-yukleme sirasinda degil, cagri
        # aninda ceker (tools paketi ici import sirasi kirilganligini onler).
        from tools.observation import ToolObservation
        from tools.runner import run_tool
        tool = self._tools.get(name)
        if tool is None:
            return ToolObservation(ok=False, tool=name,
                                   content=f"bilinmeyen tool: {name}",
                                   error=f"unknown tool: {name}")
        return run_tool(tool, args, ctx)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


# Modul-seviyesi singleton: uygulama genelinde tek kayit defteri.
registry = ToolRegistry()
