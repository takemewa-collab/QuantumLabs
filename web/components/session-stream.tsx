"use client";

import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";

type ConnState = "connecting" | "open" | "reconnecting" | "done";

interface StreamEvent {
  kind: string; // "user" | "assistant" | "observation" | "done" | "approval_needed" | ...
  parsed: Record<string, unknown> | null;
  raw: string;
}

interface Action {
  thought?: string;
  tool?: string;
  args?: Record<string, unknown>;
}

// Model action'i (ham JSON, bazen ```json fence'li) -> {thought, tool, args}.
function parseAction(content: string): Action | null {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start === -1 || end <= start) return null;
  try {
    return JSON.parse(content.slice(start, end + 1)) as Action;
  } catch {
    return null;
  }
}

export function SessionStream({ id }: { id: string }) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [conn, setConn] = useState<ConnState>("connecting");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!id) return;
    const es = new EventSource(eventsUrl(id));

    const push = (kind: string, data: string) => {
      let parsed: Record<string, unknown> | null = null;
      try {
        parsed = JSON.parse(data) as Record<string, unknown>;
      } catch {
        parsed = null;
      }
      const resolvedKind =
        kind === "message"
          ? (parsed?.type as string | undefined) ?? "unknown"
          : kind;
      setEvents((prev) => [...prev, { kind: resolvedKind, parsed, raw: data }]);
    };

    es.onopen = () => setConn("open");
    es.onmessage = (e) => push("message", e.data);

    // approval_needed: UI YOK (v0.5.1-c). Sadece logla + gorsel statik kutu.
    es.addEventListener("approval_needed", (e) => {
      const data = (e as MessageEvent).data as string;
      console.log("approval_needed", data);
      push("approval_needed", data);
    });

    es.addEventListener("end", (e) => {
      push("done", (e as MessageEvent).data as string);
      setConn("done");
      es.close();
    });

    es.onerror = () => {
      setConn((s) => (s === "done" ? s : "reconnecting"));
    };

    return () => es.close();
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 py-4">
        <h1 className="text-sm font-medium text-foreground">Session</h1>
        <code className="font-mono text-xs text-muted-foreground">{id}</code>
        {conn === "reconnecting" && (
          <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs text-muted-foreground">
            reconnecting…
          </span>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-5 pb-16 pr-2">
          {events.length === 0 && (
            <p className="text-sm text-muted-foreground">Waiting for events…</p>
          )}
          {events.map((ev, i) => (
            <EventRow key={i} ev={ev} />
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  );
}

function EventRow({ ev }: { ev: StreamEvent }) {
  const { kind, parsed, raw } = ev;
  const content = (parsed?.content as string | undefined) ?? "";

  if (kind === "user") {
    return (
      <div className="space-y-1">
        <div className="text-xs text-muted-foreground">task</div>
        <Paragraph text={content} />
      </div>
    );
  }

  if (kind === "assistant") {
    const action = parseAction(content);
    if (!action) return <Paragraph text={content} />;
    return (
      <div className="space-y-2">
        {action.thought && <Paragraph text={action.thought} />}
        {action.tool && action.tool !== "final" && (
          <ToolChip tool={action.tool} args={action.args} />
        )}
      </div>
    );
  }

  if (kind === "observation") {
    const tool = parsed?.tool as string | undefined;
    return (
      <div className="ml-4 rounded-[16px] bg-surface px-4 py-3">
        {tool && <div className="mb-1 text-xs text-muted-foreground">{tool}</div>}
        <div className="whitespace-pre-wrap break-words text-sm text-foreground">
          {content}
        </div>
      </div>
    );
  }

  if (kind === "done") {
    const result = parsed?.result as string | undefined;
    return (
      <div className="py-3 text-center text-xs text-muted-foreground">
        <span className="text-brand">✓</span>{" "}
        {result ? `done — ${result}` : "done"}
      </div>
    );
  }

  if (kind === "approval_needed") {
    return <ApprovalBox parsed={parsed} />;
  }

  // Bilinmeyen tur: mono blok, surface (drop etme).
  return (
    <pre className="overflow-x-auto rounded-[16px] bg-surface p-3 font-mono text-xs text-muted-foreground">
      {raw}
    </pre>
  );
}

function Paragraph({ text }: { text: string }) {
  return (
    <p className="whitespace-pre-wrap break-words text-[15px] leading-7 text-foreground">
      {text}
    </p>
  );
}

function ToolChip({
  tool,
  args,
}: {
  tool: string;
  args?: Record<string, unknown>;
}) {
  const argStr = args ? JSON.stringify(args, null, 2) : "";
  return (
    <details className="group">
      <summary className="inline-flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-full bg-surface px-3 py-1 font-mono text-xs text-foreground">
        <span className="text-muted-foreground transition-transform group-open:rotate-90">
          ›
        </span>
        {tool}
      </summary>
      {argStr && (
        <pre className="mt-2 overflow-x-auto rounded-[16px] bg-surface p-3 font-mono text-xs text-muted-foreground">
          {argStr}
        </pre>
      )}
    </details>
  );
}

// approval_needed — transcript'teki TEK cerceveli oge. GORSEL ONLY (buton/fetch v0.5.1-c).
function ApprovalBox({ parsed }: { parsed: Record<string, unknown> | null }) {
  const payload = (parsed?.payload ?? {}) as Record<string, unknown>;
  const isCommand = (parsed?.kind ?? "") === "command";
  const command = payload.command as string | undefined;
  const path = payload.path as string | undefined;
  const summary =
    (payload.summary as string | undefined) ??
    (isCommand ? "command approval" : "write approval");

  return (
    <div className="rounded-[16px] border border-border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm text-foreground">{summary}</span>
        <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs text-amber-500">
          <span aria-hidden>●</span> pending
        </span>
      </div>
      {command ? (
        <pre className="overflow-x-auto rounded-[12px] bg-surface p-3 font-mono text-xs text-foreground">
          {command}
        </pre>
      ) : (
        path && (
          <div className="font-mono text-xs text-muted-foreground">{path}</div>
        )
      )}
      <div className="mt-3 text-xs text-muted-foreground">
        approval pending — UI lands in v0.5.1-c
      </div>
    </div>
  );
}
