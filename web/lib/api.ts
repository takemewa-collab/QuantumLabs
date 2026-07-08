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

// Follow-up (v0.6.0): var olan session'a devam mesaji. Ayni session_id'ye yazar
// -> stream ayni transcript'i tail eder. Donusteki task_id yeni tur; session_id AYNI.
export async function sendFollowup(
  sessionId: string,
  task: string
): Promise<CreateTaskResponse> {
  const res = await fetch(
    `${API_BASE}/tasks/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ task }),
    }
  );
  if (!res.ok) {
    throw new Error(`sendFollowup failed: ${res.status}`);
  }
  return res.json();
}

// Geri bildirim (self-improvement yakiti): 👍/👎 -> feedback.jsonl. Best-effort;
// hata UI'yi bozmasin (cagiran tarafta yakalanir).
export async function sendFeedback(
  sessionId: string,
  rating: "up" | "down",
  note?: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/tasks/${encodeURIComponent(sessionId)}/feedback`,
    {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ rating, note }),
    }
  );
  if (!res.ok) {
    throw new Error(`sendFeedback failed: ${res.status}`);
  }
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
// after: istemcinin zaten gordugu transcript satir sayisi. Follow-up'ta ayni
// session'a yeniden baglanirken verilir -> backend o satirlari atlar, sadece
// yeni turu yollar (bastan tekrar akmaz). 0/undefined -> tam replay + tail.
export function eventsUrl(id: string, after = 0): string {
  const params = new URLSearchParams();
  if (after > 0) params.set("after", String(after));
  if (API_KEY) params.set("key", API_KEY);
  const qs = params.toString();
  return `${API_BASE}/tasks/${encodeURIComponent(id)}/stream${qs ? `?${qs}` : ""}`;
}
