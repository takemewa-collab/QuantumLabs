"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { listSessions, type SessionSummary } from "@/lib/api";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export function AppSidebar() {
  const pathname = usePathname();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [query, setQuery] = useState("");

  // Fetch on navigation only (no polling).
  useEffect(() => {
    let active = true;
    listSessions().then((s) => {
      if (active) setSessions(s);
    });
    return () => {
      active = false;
    };
  }, [pathname]);

  const groups = useMemo(() => groupByDate(sessions, query), [sessions, query]);
  const hasAny = sessions.length > 0;
  const hasMatches = groups.some((g) => g.items.length > 0);

  return (
    <Sidebar>
      <SidebarHeader className="gap-2.5 px-3 py-3">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          QuantumLabs
        </Link>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search sessions"
            aria-label="Search sessions"
            className="h-8 w-full rounded-lg border border-border bg-surface pl-8 pr-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  render={<Link href="/new" />}
                  isActive={pathname === "/new"}
                >
                  <Plus className="size-4" />
                  <span>New task</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {!hasAny && (
          <div className="px-4 py-6 text-xs leading-5 text-muted-foreground">
            No sessions yet — start your first task.
          </div>
        )}
        {hasAny && !hasMatches && (
          <div className="px-4 py-3 text-xs text-muted-foreground">No matches.</div>
        )}

        {groups.map((g) =>
          g.items.length === 0 ? null : (
            <SidebarGroup key={g.label}>
              <SidebarGroupLabel>{g.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {g.items.map((s) => (
                    <SidebarMenuItem key={s.id}>
                      <SidebarMenuButton
                        render={<Link href={`/sessions/${s.id}`} />}
                        isActive={pathname === `/sessions/${s.id}`}
                      >
                        <span className="truncate">{s.title}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )
        )}
      </SidebarContent>
    </Sidebar>
  );
}

interface Group {
  label: string;
  items: SessionSummary[];
}

// Titl'a gore filtrele, sonra tarihe gore grupla (Today / Yesterday / Previous 7 days / Older).
function groupByDate(sessions: SessionSummary[], query: string): Group[] {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? sessions.filter((s) => s.title.toLowerCase().includes(q))
    : sessions;

  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  ).getTime();
  const DAY = 86_400_000;

  const today: SessionSummary[] = [];
  const yesterday: SessionSummary[] = [];
  const week: SessionSummary[] = [];
  const older: SessionSummary[] = [];

  for (const s of filtered) {
    const t = new Date(s.created_at).getTime();
    if (Number.isNaN(t) || t < startOfToday - 7 * DAY) older.push(s);
    else if (t >= startOfToday) today.push(s);
    else if (t >= startOfToday - DAY) yesterday.push(s);
    else week.push(s);
  }

  return [
    { label: "Today", items: today },
    { label: "Yesterday", items: yesterday },
    { label: "Previous 7 days", items: week },
    { label: "Older", items: older },
  ];
}
