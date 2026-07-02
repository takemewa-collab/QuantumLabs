"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createTask } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

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
    <div className="mx-auto w-full max-w-2xl p-6">
      <Card>
        <CardHeader>
          <CardTitle>New task</CardTitle>
          <CardDescription>
            Describe a task for the agent. ⌘/Ctrl + Enter to submit.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="e.g. read README.md and summarise the project"
            rows={6}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onSubmit();
            }}
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button onClick={onSubmit} disabled={submitting || !task.trim()}>
            {submitting ? "Submitting…" : "Submit task"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
