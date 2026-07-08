"use client";

import { useEffect, useRef, useState } from "react";
import { eventsUrl, sendFollowup, sendFeedback } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Composer } from "@/components/composer";

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

// Optimistic mesaji /new'den session'a tasiyan sessionStorage anahtari.
const pendingKey = (id: string) => `ql:pending:${id}`;

// /new'den tasinan optimistic mesaji oku (SSR-guvenli). Silme MOUNT effect'inde.
function readCarried(id: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const c = sessionStorage.getItem(pendingKey(id));
    return c ? [c] : [];
  } catch {
    return [];
  }
}

// Reasoning-model <think>…</think> bloklarini (kapali VE ac-kalmis) temizle.
// Kullaniciya ic dusunme sizmasin — sadece nihai icerik gorunsun.
function stripThink(text: string): string {
  return text
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/<think>[\s\S]*$/i, "")
    .trim();
}

// Tool -> insan-okunur aktivite ("arka planda ne oluyor"). running/done ayri
// ifade; edit basarisi "Applied". detail = args'tan baglam (dosya/komut/sorgu).
type StepState = { state: "running" | "waiting_approval" | "done"; ok?: boolean };

const ACTIVITY: Record<
  string,
  { icon: string; running: string; done: string; edit?: boolean }
> = {
  search_code: { icon: "🔍", running: "searching project…", done: "searched project" },
  search_memory: { icon: "🧠", running: "searching memory…", done: "searched memory" },
  read_file: { icon: "📖", running: "reading file…", done: "read file" },
  run_command: { icon: "⌘", running: "running command…", done: "ran command" },
  write_file: { icon: "✏️", running: "generating patch…", done: "Applied", edit: true },
  replace_text: { icon: "✏️", running: "generating patch…", done: "Applied", edit: true },
};

function activityDetail(tool: string, args?: Record<string, unknown>): string {
  if (!args) return "";
  const s = (v: unknown) => (typeof v === "string" ? v : "");
  if (tool === "read_file" || tool === "write_file" || tool === "replace_text")
    return s(args.path);
  if (tool === "run_command") return s(args.command).slice(0, 80);
  if (tool === "search_code" || tool === "search_memory") return s(args.query).slice(0, 60);
  return "";
}

// Bir assistant tool-adiminin durumu: sonrasinda observation geldiyse done
// (ok?), araya approval_needed girdiyse waiting_approval, yoksa running.
function stepStatus(events: StreamEvent[], i: number): StepState {
  let sawApproval = false;
  for (let j = i + 1; j < events.length; j++) {
    const k = events[j].kind;
    if (k === "observation")
      return { state: "done", ok: events[j].parsed?.ok !== false };
    if (k === "approval_needed") sawApproval = true;
    if (k === "assistant" || k === "user" || k === "done") break;
  }
  return { state: sawApproval ? "waiting_approval" : "running" };
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

export function ChatSession({ id }: { id: string }) {
  // pending/awaiting lazy init: /new'den tasinan optimistic mesaj varsa MOUNT'ta
  // hemen gorunur (component key={id} ile remount oldugu icin id basina temiz).
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [pending, setPending] = useState<string[]>(() => readCarried(id));
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // awaiting: bu turda agent'in ILK yanitini bekliyoruz (cold-start gostergesi).
  const [awaiting, setAwaiting] = useState<boolean>(() => readCarried(id).length > 0);
  const [turn, setTurn] = useState(0); // her yeni user mesajinda artar (indicator remount)
  const [reconnect, setReconnect] = useState(0); // follow-up sonrasi ES'i yeniden ac
  const [feedback, setFeedback] = useState<null | "up" | "down">(null); // bu turun 👍/👎'i

  const linesSeen = useRef(0); // gorulen transcript satiri (after offset icin)
  const seenRaw = useRef<Set<string>>(new Set()); // dedup: her satir/approval BIR kez
  const doneRef = useRef(false); // bu stream 'end' aldi mi (onerror'u sustur)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  // Tasinan optimistic mesaji tek seferlik temizle (yenilemede stale kalmasin;
  // stream gercek user event'ini zaten getirir). setState YOK -> saf yan etki.
  useEffect(() => {
    try {
      sessionStorage.removeItem(pendingKey(id));
    } catch {
      // yoksa gec
    }
  }, [id]);

  // EventSource: [id, reconnect] degisince (re)ac. after = zaten gorulen satir
  // sayisi -> follow-up reconnect'te transcript bastan AKMAZ, sadece yeni tur gelir.
  useEffect(() => {
    if (!id) return;
    doneRef.current = false; // her (re)acilis taze bir stream denemesi
    // after = zaten gorulen satir sayisi -> reconnect'te transcript bastan AKMAZ,
    // kaldigi yerden devam eder (native ES stale after=0 ile replay ederdi -> dup).
    const es = new EventSource(eventsUrl(id, linesSeen.current));

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

      // DEDUP (kurşungeçirmez): ayni transcript satiri/approval iki kez gelirse
      // (herhangi bir reconnect replay'i) ikinciyi YOK say. linesSeen SADECE yeni
      // satirda ilerler -> after offset hep dogru hizada kalir.
      if (kind === "message") {
        if (seenRaw.current.has(data)) return;
        seenRaw.current.add(data);
        linesSeen.current += 1;
      } else if (resolvedKind === "approval_needed") {
        const k = "appr:" + String(parsed?.approval_id ?? data);
        if (seenRaw.current.has(k)) return;
        seenRaw.current.add(k);
      }

      if (resolvedKind === "user") {
        // Yeni tur basladi: cold-start bekleyisini ac, indicator'i remount et.
        setAwaiting(true);
        setTurn((t) => t + 1);
        setFeedback(null); // yeni tur -> yeni yanit -> yeni geri bildirim hakki
        // Optimistic esini uzlastir: ayni metinli ilk pending'i dus.
        const content = ((parsed?.content as string | undefined) ?? "").trim();
        setPending((p) => {
          const i = p.findIndex((m) => m.trim() === content);
          if (i === -1) return p;
          return [...p.slice(0, i), ...p.slice(i + 1)];
        });
      } else if (resolvedKind === "assistant" || resolvedKind === "observation") {
        setAwaiting(false); // agent yanit vermeye basladi
      }

      setEvents((prev) => [...prev, { kind: resolvedKind, parsed, raw: data }]);
    };

    es.onopen = () => setConn("open");
    es.onmessage = (e) => push("message", e.data);

    es.addEventListener("approval_needed", (e) => {
      push("approval_needed", (e as MessageEvent).data as string);
    });

    es.addEventListener("end", (e) => {
      push("done", (e as MessageEvent).data as string);
      doneRef.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      setAwaiting(false);
      setConn("done");
      es.close();
    });

    es.onerror = () => {
      if (doneRef.current) return; // normal kapanis -> reconnect YOK
      setConn((s) => (s === "done" ? s : "reconnecting"));
      // Native ES stale URL (after=0) ile replay ederdi. Onun yerine: kapat ve
      // linesSeen'den DEVAM ederek yeniden ac (replay degil, resume). Kucuk backoff.
      es.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(
        () => setReconnect((r) => r + 1),
        1500
      );
    };

    return () => {
      es.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
    // linesSeen/refs deps'te degil (kasitli); reconnect bump'i ES'i yeniden acar.
  }, [id, reconnect]);

  // Yeni icerik geldikce en alta kaydir.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, pending, awaiting]);

  // Alttaki composer -> ayni session'a follow-up. conn 'done' degilken (tur
  // suruyor) kapali: tek transcript'e es zamanli iki agent yazmasin.
  const idle = conn === "done";
  const canSend = idle && !sending;

  // 👍/👎 -> feedback.jsonl (self-improvement yakiti). Optimistic: UI hemen
  // isaretler; POST best-effort (hata olsa da isaret kalir).
  async function rate(r: "up" | "down") {
    if (feedback) return;
    setFeedback(r);
    try {
      await sendFeedback(id, r);
    } catch {
      // best-effort — isaret UI'da kalir
    }
  }

  async function submitFollowup() {
    const text = draft.trim();
    if (!text || !canSend) return;
    setSending(true);
    setError(null);
    // Optimistic: mesaji hemen goster, kutuyu temizle/refocus (persistent).
    setPending((p) => [...p, text]);
    setAwaiting(true);
    setTurn((t) => t + 1);
    setFeedback(null);
    setDraft("");
    composerRef.current?.focus();
    try {
      await sendFollowup(id, text);
      // Stream'i after offset'le yeniden ac -> yeni tur transcript'ten tail edilir.
      setReconnect((r) => r + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send message");
      setPending((p) => p.slice(0, -1)); // optimistic'i geri al
      setAwaiting(false);
    } finally {
      setSending(false);
    }
  }

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

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-5 pb-6 pr-2">
          {events.length === 0 && pending.length === 0 && conn !== "done" && (
            <p className="text-sm text-muted-foreground">Waiting for events…</p>
          )}
          {events.map((ev, i) => (
            <EventRow
              key={i}
              ev={ev}
              step={ev.kind === "assistant" ? stepStatus(events, i) : undefined}
            />
          ))}
          {/* Optimistic user mesajlari (transcript'ten donene dek) */}
          {pending.map((text, i) => (
            <div key={`pending-${i}`} className="space-y-1">
              <div className="text-xs text-muted-foreground">task</div>
              <Paragraph text={text} />
            </div>
          ))}
          {awaiting && conn !== "done" && <ThinkingIndicator key={turn} />}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* Alt sabit composer — persistent; tur suruyorken kapali */}
      <div className="shrink-0 pb-4 pt-2">
        {/* Geri bildirim: tur bitince (idle) bu yanit yardimci oldu mu? */}
        {idle && events.length > 0 && (
          <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
            {feedback ? (
              <span>Teşekkürler — geri bildirim kaydedildi.</span>
            ) : (
              <>
                <span>Bu yanıt yardımcı oldu mu?</span>
                <button
                  type="button"
                  onClick={() => rate("up")}
                  aria-label="Yardımcı oldu"
                  className="rounded-md px-1.5 py-0.5 transition-colors hover:bg-accent"
                >
                  👍
                </button>
                <button
                  type="button"
                  onClick={() => rate("down")}
                  aria-label="Yardımcı olmadı"
                  className="rounded-md px-1.5 py-0.5 transition-colors hover:bg-accent"
                >
                  👎
                </button>
              </>
            )}
          </div>
        )}
        {error && <p className="mb-2 text-sm text-destructive">{error}</p>}
        <Composer
          ref={composerRef}
          value={draft}
          onChange={setDraft}
          onSubmit={submitFollowup}
          disabled={!canSend}
          placeholder={
            idle ? "Reply to the agent…" : "Agent is working — please wait…"
          }
        />
      </div>
    </div>
  );
}

// Ziplayan uc-nokta spinner (thinking + calisan aktivite adiminda ortak).
function Dots() {
  return (
    <span className="flex gap-1" aria-hidden>
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
    </span>
  );
}

// "thinking…" gostergesi: 6 sn sonra cold-start bakisina gecer (ilk istek 30-60s).
// key={turn} ile her yeni turda remount -> 6 sn sayaci basa sarar.
function ThinkingIndicator() {
  const [cold, setCold] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setCold(true), 6000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Dots />
      <span>
        {cold ? "starting model… first response can take 30–60s" : "thinking…"}
      </span>
    </div>
  );
}

// "Arka planda ne oluyor" — tool adimini insan-okunur aktivite olarak gosterir.
// running: spinner + "searching project…"; done: ✓ + "read file registry.py";
// edit basarisi: "Applied"; onay bekliyor: "waiting approval…". Args katlanabilir.
function ActivityRow({
  tool,
  args,
  step,
}: {
  tool: string;
  args?: Record<string, unknown>;
  step: StepState;
}) {
  const meta = ACTIVITY[tool];
  const detail = activityDetail(tool, args);
  const running = step.state === "running";
  const waiting = step.state === "waiting_approval";
  const done = step.state === "done";
  const failed = done && step.ok === false;

  let label: string;
  if (waiting) label = "waiting approval…";
  else if (running) label = meta?.running ?? `${tool}…`;
  else if (failed) label = meta?.edit ? "not applied" : meta?.done ?? tool;
  else label = meta?.done ?? tool;

  const argStr = args ? JSON.stringify(args, null, 2) : "";

  return (
    <details className="group">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-2 text-sm">
        <span aria-hidden>{meta?.icon ?? "•"}</span>
        <span className={done && !failed ? "text-muted-foreground" : "text-foreground"}>
          {label}
          {detail && <span className="ml-1 font-mono text-xs text-muted-foreground">{detail}</span>}
        </span>
        {running && <Dots />}
        {waiting && <span className="text-amber-500" aria-hidden>●</span>}
        {done && !failed && <span className="text-brand" aria-hidden>✓</span>}
        {failed && <span className="text-destructive" aria-hidden>✗</span>}
      </summary>
      {argStr && (
        <pre className="mt-2 overflow-x-auto rounded-[16px] bg-surface p-3 font-mono text-xs text-muted-foreground">
          {argStr}
        </pre>
      )}
    </details>
  );
}

function EventRow({ ev, step }: { ev: StreamEvent; step?: StepState }) {
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
    const clean = stripThink(content);
    const action = parseAction(clean);
    // JSON action yok -> duz metin cevap (temizlenmis) goster.
    if (!action) return clean ? <Paragraph text={clean} /> : null;

    // FINAL: kullaniciya ASIL cevabi goster (ic dusunceyi DEGIL).
    if (action.tool === "final") {
      const answer = stripThink(
        String(action.args?.answer ?? action.thought ?? clean)
      );
      return answer ? <Paragraph text={answer} /> : null;
    }

    // Ara adim (tool cagrisi): "arka planda ne oluyor" aktivite satiri.
    if (action.tool) {
      return (
        <ActivityRow
          tool={action.tool}
          args={action.args}
          step={step ?? { state: "running" }}
        />
      );
    }
    return null;
  }

  if (kind === "observation") {
    // Tool sonucu (dosya icerigi / arama sonuclari / diff). Ust satirdaki
    // ActivityRow zaten aracı adlandiriyor -> burada etiket tekrarina gerek yok.
    return (
      <div className="ml-4 rounded-[16px] bg-surface px-4 py-3">
        <div className="whitespace-pre-wrap break-words text-sm text-foreground">
          {content}
        </div>
      </div>
    );
  }

  if (kind === "done") {
    // Cevap artik asistan balonunda gorunuyor -> burada ham result'i TEKRAR
    // basma (icinde <think> olabilir). Sadece ince bir bitis isareti; hata varsa hata.
    const status = parsed?.status as string | undefined;
    const error = parsed?.error as string | undefined;
    if (status === "failed") {
      return (
        <div className="py-2 text-center text-xs text-destructive">
          ✗ {error || "failed"}
        </div>
      );
    }
    return (
      <div className="py-2 text-center text-xs text-muted-foreground">
        <span className="text-brand">✓</span> done
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

// approval_needed — GORSEL ONLY (buton/fetch v0.5.1-c).
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
