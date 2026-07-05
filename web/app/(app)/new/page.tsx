"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUp } from "lucide-react";
import { createTask } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const EXAMPLES = [
  "Summarize the README",
  "Find TODOs in the codebase",
  "Explain tools/registry.py",
];

export default function NewTask() {
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedId, setStartedId] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);

  function fill(text: string) {
    setTask(text);
    ref.current?.focus();
  }

  async function onSubmit() {
    const trimmed = task.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createTask(trimmed);
      // Persistent composer: box stays open, clears, refocuses; no navigation.
      setStartedId(res.task_id);
      setTask("");
      ref.current?.focus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start task");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex w-full flex-1 flex-col items-center justify-center gap-6">
      <h1 className="text-2xl font-medium tracking-tight">What should the agent do?</h1>

      <div className="w-full">
        {/* composer card — focus ring lives on the CARD; textarea is borderless */}
        <div className="rounded-[20px] border border-border bg-surface shadow-sm transition-shadow focus-within:ring-1 focus-within:ring-ring">
          <Textarea
            ref={ref}
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Message the agent…"
            rows={3}
            autoFocus
            onKeyDown={(e) => {
              // Enter -> send; Shift+Enter -> newline. isComposing: don't swallow IME Enter.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                onSubmit();
              }
            }}
            className="min-h-[80px] resize-none border-0 bg-transparent px-4 pt-3.5 text-base shadow-none focus-visible:border-0 focus-visible:ring-0"
          />
          <div className="flex items-center justify-between px-3 pb-2.5">
            <span className="text-xs text-muted-foreground">
              Enter to send · Shift+Enter for a newline
            </span>
            <Button
              onClick={onSubmit}
              disabled={submitting || !task.trim()}
              size="icon"
              aria-label="Send"
              className="size-8 rounded-full bg-brand text-primary-foreground hover:opacity-90 disabled:opacity-40"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
        </div>

        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

        {startedId && (
          <div className="mt-3">
            <Link
              href={`/sessions/${startedId}`}
              className="inline-flex items-center gap-1 text-sm text-brand hover:underline"
            >
              Task started · open session <ArrowRight className="size-3.5" />
            </Link>
          </div>
        )}

        {/* example-task chips (fill the input on click) */}
        {!task.trim() && !startedId && (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => fill(ex)}
                className="rounded-full border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
