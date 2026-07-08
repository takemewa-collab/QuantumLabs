"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createTask } from "@/lib/api";
import { Composer } from "@/components/composer";

const EXAMPLES = [
  "Summarize the README",
  "Find TODOs in the codebase",
  "Explain tools/registry.py",
];

export default function NewTask() {
  const router = useRouter();
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      // Optimistic mesaji session'a tasi: chat yuzeyi mount olur olmaz gosterir,
      // stream cold-start'ta sessiz kalsa bile mesaj aninda gorunur.
      try {
        sessionStorage.setItem(`ql:pending:${res.session_id}`, trimmed);
      } catch {
        // sessionStorage yoksa sorun degil — stream user event'ini yine de getirir.
      }
      // Ayri sayfaya LINK YOK: kullaniciyi dogrudan session gorunumune tasi.
      router.push(`/sessions/${res.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start task");
      setSubmitting(false);
    }
    // Basari halinde submitting'i BIRAKMA: navigasyon suruyor, kutu kilitli kalsin.
  }

  return (
    <div className="flex w-full flex-1 flex-col items-center justify-center gap-6">
      <h1 className="text-2xl font-medium tracking-tight">
        What should the agent do?
      </h1>

      <div className="w-full">
        <Composer
          ref={ref}
          value={task}
          onChange={setTask}
          onSubmit={onSubmit}
          disabled={submitting}
          autoFocus
        />

        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

        {/* example-task chips (fill the input on click) */}
        {!task.trim() && (
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
