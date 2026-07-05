// QuantumLabs — tek fetch katmani. TUM API cagrilari buradan gecer.
//
// NOT (route uyumu): backend (FastAPI) endpoint'leri /tasks altinda:
//   POST /tasks              -> { task_id, session_id, transcript_path }
//   GET  /tasks              -> SessionSummary[]  (== GET /sessions alias)
//   GET  /tasks/{id}         -> task kaydi
//   GET  /tasks/{id}/stream  -> SSE (text/event-stream)
// [id] = task_id. listSessions hata/yok durumunda [] doner (bos sidebar).

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface CreateTaskResponse {
  task_id: string;
  session_id: string;
  transcript_path: string;
}

export interface TaskRecord {
  id: string;
  status: string;
  session_id: string;
  workspace?: string;
  result?: string | null;
  error?: string | null;
}

// GET /tasks (list) donusu — GET /tasks/{id}'den FARKLI sema.
export interface SessionSummary {
  id: string;
  created_at: string;
  title: string;
}

export async function createTask(task: string): Promise<CreateTaskResponse> {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
  if (!res.ok) {
    throw new Error(`createTask failed: ${res.status}`);
  }
  return res.json();
}

export async function getTask(id: string): Promise<TaskRecord | null> {
  try {
    const res = await fetch(`${API_BASE}/tasks/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as TaskRecord;
  } catch {
    return null;
  }
}

export async function listSessions(): Promise<SessionSummary[]> {
  // Backend hata/yok -> [] (bos sidebar). GET /tasks == GET /sessions (alias).
  try {
    const res = await fetch(`${API_BASE}/tasks`, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data as SessionSummary[];
    if (Array.isArray(data?.tasks)) return data.tasks as SessionSummary[];
    return [];
  } catch {
    return [];
  }
}

// SSE endpoint URL'i (EventSource icin).
export function eventsUrl(id: string): string {
  return `${API_BASE}/tasks/${id}/stream`;
}
