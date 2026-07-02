"use client";

import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";

type ConnState = "connecting" | "open" | "reconnecting" | "done";

interface StreamEvent {
  kind: string; // parsed.type ("user" | "assistant" | "observation" | "done" | ...) veya "approval_needed"
  parsed: Record<string, unknown> | null;
  raw: string;
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
    es.onmessage = (e) => push("message", e.data); // transcript event'leri (data:)

    // approval_needed: UI YOK (v0.5.1-c). Sadece logla + statik satir.
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
      // EventSource kendisi otomatik yeniden baglanir; done degilse rozet goster.
      setConn((s) => (s === "done" ? s : "reconnecting"));
    };

    return () => es.close();
  }, [id]);

  // append-only + otomatik en alta kaydir
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="flex h-[calc(100vh-2.5rem)] flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold">Session</h1>
        <code className="text-xs text-muted-foreground">{id}</code>
        {conn === "reconnecting" && (
          <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs text-yellow-800">
            reconnecting…
          </span>
        )}
        {conn === "open" && (
          <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
            live
          </span>
        )}
        {conn === "done" && (
          <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
            done
          </span>
        )}
      </div>

      <ScrollArea className="flex-1 rounded border">
        <div className="space-y-2 p-3">
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

  if (kind === "approval_needed") {
    // v0.5.1-c: gercek onay karti. Simdilik statik tek satir.
    return (
      <div className="text-sm italic text-muted-foreground">
        approval pending — UI lands in v0.5.1-c
      </div>
    );
  }
  if (kind === "user") {
    return <Bubble label="task" text={content || raw} />;
  }
  if (kind === "assistant") {
    return <Bubble label="assistant" text={content || raw} />;
  }
  if (kind === "observation") {
    const tool = (parsed?.tool as string | undefined) ?? "?";
    return <Bubble label={`tool: ${tool}`} text={content || raw} />;
  }
  if (kind === "done") {
    const result = parsed?.result as string | undefined;
    return (
      <div className="text-sm font-medium text-green-700">
        ✓ done{result ? ` — ${result}` : ""}
      </div>
    );
  }
  // Bilinmeyen tur: ham JSON'u muted blokta goster (ASLA drop etme).
  return (
    <pre className="overflow-x-auto rounded bg-muted p-2 text-xs text-muted-foreground">
      {raw}
    </pre>
  );
}

function Bubble({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border p-2">
      <div className="mb-1 text-xs uppercase text-muted-foreground">{label}</div>
      <div className="whitespace-pre-wrap break-words text-sm">{text}</div>
    </div>
  );
}
