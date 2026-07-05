"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { createTask } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function NewTask() {
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedId, setStartedId] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);

  async function onSubmit() {
    const trimmed = task.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createTask(trimmed);
      // Persistent composer: input acik + focused kalir, navigate ETME.
      // Baslatilan oturuma link gosterilir (sidebar da guncellenir).
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
    <div className="flex w-full flex-1 flex-col items-center justify-center gap-8">
      <h1 className="text-2xl font-medium tracking-tight">Start a task</h1>

      <div className="w-full">
        <Textarea
          ref={ref}
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="What should the agent do?  (Enter to send · Shift+Enter for a newline)"
          rows={4}
          autoFocus
          onKeyDown={(e) => {
            // Enter -> send; Shift+Enter -> newline (default).
            // isComposing: don't swallow Enter mid-IME/dead-key composition.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSubmit();
            }
          }}
          className="min-h-[120px] resize-none rounded-[16px] border-border bg-surface px-4 py-3 text-base shadow-sm focus-visible:ring-1 focus-visible:ring-ring"
        />
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="min-h-5 text-sm">
            {startedId && (
              <Link
                href={`/sessions/${startedId}`}
                className="inline-flex items-center gap-1 text-brand hover:underline"
              >
                Task started · open session <ArrowRight className="size-3.5" />
              </Link>
            )}
          </div>
          <Button
            onClick={onSubmit}
            disabled={submitting || !task.trim()}
            className="rounded-full px-6"
          >
            {submitting ? "Starting…" : "Start"}
          </Button>
        </div>
      </div>
    </div>
  );
}
