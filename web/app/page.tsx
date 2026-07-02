"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createTask } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function Home() {
  const router = useRouter();
  const [task, setTask] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    const trimmed = task.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createTask(trimmed);
      router.push(`/sessions/${res.task_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "submit failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex w-full flex-1 flex-col items-center justify-center gap-8">
      <h1 className="text-2xl font-medium tracking-tight text-foreground">
        Agent&apos;a bir görev ver
      </h1>

      <div className="w-full">
        <Textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Ne yapmasını istersin? (⌘/Ctrl + Enter ile gönder)"
          rows={4}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onSubmit();
          }}
          className="min-h-[120px] resize-none rounded-[16px] border-border bg-background px-4 py-3 text-base shadow-sm focus-visible:ring-0"
        />
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <div className="mt-4 flex justify-end">
          <Button
            onClick={onSubmit}
            disabled={submitting || !task.trim()}
            className="rounded-full px-6"
          >
            {submitting ? "Gönderiliyor…" : "Gönder"}
          </Button>
        </div>
      </div>
    </div>
  );
}
