// QuantumLabs — tek fetch katmani. TUM API cagrilari buradan gecer.
//
// NOT (route uyumu): backend (FastAPI) endpoint'leri /tasks altinda:
//   POST /tasks              -> { task_id, session_id, transcript_path }
//   GET  /tasks              -> SessionSummary[]  (== GET /sessions alias)
//   GET  /tasks/{id}         -> task kaydi
//   GET  /tasks/{id}/stream  -> SSE (text/event-stream)
// URL'lerdeki {id} = session_id (kalici, tek kimlik). Backend geriye-uyum icin
// hem task_id hem session_id kabul eder; frontend YALNIZ session_id yayar.
// listSessions hata/yok durumunda [] doner (bos sidebar).

// API base: NEXT_PUBLIC_API_URL varsa onu, yoksa (geriye uyum) eski
// NEXT_PUBLIC_API_BASE_URL, o da yoksa dev default localhost:8000.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

// Opsiyonel API anahtari: set ise tum fetch'lere Authorization: Bearer eklenir.
// EventSource custom header gonderemedigi icin SSE'de ?key= query param kullanilir.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(
  base: Record<string, string> = {}
): Record<string, string> {
  return API_KEY ? { ...base, Authorization: `Bearer ${API_KEY}` } : base;
}

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
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ task }),
  });
  if (!res.ok) {
    throw new Error(`createTask failed: ${res.status}`);
  }
  return res.json();
}

export async function getTask(id: string): Promise<TaskRecord | null> {
  try {
    const res = await fetch(`${API_BASE}/tasks/${id}`, {
      cache: "no-store",
      headers: authHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as TaskRecord;
  } catch {
    return null;
  }
}

export async function listSessions(): Promise<SessionSummary[]> {
  // Backend hata/yok -> [] (bos sidebar). GET /tasks == GET /sessions (alias).
  try {
    const res = await fetch(`${API_BASE}/tasks`, {
      cache: "no-store",
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data as SessionSummary[];
    if (Array.isArray(data?.tasks)) return data.tasks as SessionSummary[];
    return [];
  } catch {
    return [];
  }
}

// SSE endpoint URL'i (EventSource icin). API_KEY varsa ?key= ile (header YOK).
export function eventsUrl(id: string): string {
  const url = `${API_BASE}/tasks/${id}/stream`;
  return API_KEY ? `${url}?key=${encodeURIComponent(API_KEY)}` : url;
}
