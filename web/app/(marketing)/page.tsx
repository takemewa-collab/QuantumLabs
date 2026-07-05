import Link from "next/link";
import {
  Wrench,
  Server,
  RotateCcw,
  Database,
  Radio,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import { CopyButton } from "@/components/copy-button";

const GITHUB = "https://github.com/takemewa-collab/QuantumLabs";

// lucide 1.x marka ikonlarini kaldirdi -> GitHub mark'i inline SVG (dep yok).
function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 016 0C17 4.6 18 4.9 18 4.9c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}

const FEATURES = [
  {
    icon: Wrench,
    title: "Tool-calling agents",
    body: "A ReAct loop that searches the repo, reads files, writes changes, and runs commands.",
  },
  {
    icon: Server,
    title: "Fully self-hosted",
    body: "Your model, your GPU. Any OpenAI-compatible endpoint — Ollama, vLLM, or your own pod.",
  },
  {
    icon: RotateCcw,
    title: "Safe edits",
    body: "Every write is checkpointed. Roll a session back to any point with one command.",
  },
  {
    icon: Database,
    title: "Persistent memory",
    body: "RAG over past sessions; relevant context is auto-injected into new tasks.",
  },
  {
    icon: Radio,
    title: "Streaming API",
    body: "A FastAPI backend with SSE task streams — watch the tool-call loop live.",
  },
  {
    icon: ShieldCheck,
    title: "Human-in-the-loop",
    body: "Approve or deny file writes and shell commands before they ever run.",
  },
];

const TERMINAL = [
  { p: "$", t: 'ql agent "summarize the README"', tone: "prompt" },
  { p: "›", t: "search_code  query=def main", tone: "call" },
  { p: " ", t: "agents/code_agent.py:133   services/main.py:1", tone: "out" },
  { p: "›", t: "read_file  path=README.md", tone: "call" },
  { p: " ", t: "# Quantum Labs", tone: "out" },
  { p: "✓", t: 'done  "# Quantum Labs"', tone: "done" },
];

const QUICKSTART = `git clone ${GITHUB}
cd QuantumLabs
./dev.sh`;

export default function Landing() {
  return (
    <main className="min-h-svh">
      {/* nav */}
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-sm font-semibold tracking-tight">QuantumLabs</span>
        <div className="flex items-center gap-5 text-sm text-muted-foreground">
          <a href={GITHUB} className="inline-flex items-center gap-1.5 hover:text-foreground">
            <GithubMark className="size-4" /> GitHub
          </a>
          <Link href="/new" className="hover:text-foreground">
            Console
          </Link>
        </div>
      </nav>

      {/* hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 pb-20 pt-10 md:grid-cols-2 md:pt-20">
        <div>
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight md:text-5xl">
            Self-hosted AI agents that call tools, edit code, and remember.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
            Bring your own model and GPU. A tool-calling loop with safe edits,
            checkpoints, persistent RAG memory, a streaming API, and
            human-in-the-loop approvals — running entirely on your box.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/new"
              className="inline-flex items-center gap-2 rounded-full bg-brand px-5 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Get started <ArrowRight className="size-4" />
            </Link>
            <a
              href={GITHUB}
              className="inline-flex items-center gap-2 rounded-full border border-border px-5 py-2.5 text-sm transition-colors hover:bg-surface"
            >
              <GithubMark className="size-4" /> GitHub
            </a>
          </div>
        </div>

        {/* terminal demo (static, mono) */}
        <div className="rounded-[16px] border border-border bg-surface">
          <div className="flex items-center gap-1.5 border-b border-border px-4 py-3">
            <span className="size-2.5 rounded-full bg-muted-foreground/40" />
            <span className="size-2.5 rounded-full bg-muted-foreground/40" />
            <span className="size-2.5 rounded-full bg-muted-foreground/40" />
            <span className="ml-2 font-mono text-xs text-muted-foreground">
              agent — code_agent
            </span>
          </div>
          <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-6">
            {TERMINAL.map((l, i) => (
              <div key={i} className="flex gap-2">
                <span
                  className={
                    l.tone === "done" || l.tone === "prompt" || l.tone === "call"
                      ? "text-brand"
                      : "text-muted-foreground"
                  }
                >
                  {l.p}
                </span>
                <span
                  className={l.tone === "out" ? "text-muted-foreground" : "text-foreground"}
                >
                  {l.t}
                </span>
              </div>
            ))}
            <span className="ml-1 mt-1 inline-block h-4 w-[7px] animate-pulse bg-brand align-middle" />
          </pre>
        </div>
      </section>

      {/* feature grid */}
      <section className="mx-auto max-w-6xl px-6 py-8">
        <div className="grid gap-px overflow-hidden rounded-[16px] border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="bg-background p-6">
              <Icon className="size-5 text-brand" />
              <h3 className="mt-4 text-sm font-medium">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* quickstart */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-center text-lg font-medium">Run it in three commands</h2>
          <div className="mt-6 rounded-[16px] border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <span className="font-mono text-xs text-muted-foreground">bash</span>
              <CopyButton text={QUICKSTART} />
            </div>
            <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-6 text-foreground">
              <span className="text-muted-foreground">$ </span>git clone {GITHUB}
              {"\n"}
              <span className="text-muted-foreground">$ </span>cd QuantumLabs
              {"\n"}
              <span className="text-muted-foreground">$ </span>./dev.sh
            </pre>
          </div>
          <p className="mt-3 text-center text-sm text-muted-foreground">
            Then open{" "}
            <span className="font-mono text-foreground">http://localhost:3000</span>
          </p>
        </div>
      </section>

      {/* footer */}
      <footer className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 border-t border-border px-6 py-8 text-sm text-muted-foreground sm:flex-row">
        <span>QuantumLabs · q-labs.dev</span>
        <div className="flex items-center gap-5">
          <a href={GITHUB} className="inline-flex items-center gap-1.5 hover:text-foreground">
            <GithubMark className="size-4" /> GitHub
          </a>
          <span className="cursor-default opacity-60">Docs (soon)</span>
        </div>
      </footer>
    </main>
  );
}
