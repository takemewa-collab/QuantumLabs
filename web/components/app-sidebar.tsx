"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus } from "lucide-react";
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

  // Fetch on navigation only (no polling): pathname degisince bir kez cek.
  useEffect(() => {
    let active = true;
    listSessions().then((s) => {
      if (active) setSessions(s);
    });
    return () => {
      active = false;
    };
  }, [pathname]);

  return (
    <Sidebar>
      <SidebarHeader className="px-3 py-3">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          QuantumLabs
        </Link>
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

        <SidebarGroup>
          <SidebarGroupLabel>Sessions</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {sessions.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  No sessions yet
                </div>
              )}
              {sessions.map((s) => (
                <SidebarMenuItem key={s.id}>
                  <SidebarMenuButton
                    render={<Link href={`/sessions/${s.id}`} />}
                    isActive={pathname === `/sessions/${s.id}`}
                    className="h-auto py-1.5"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm">{s.title}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {formatCreated(s.created_at)}
                      </span>
                    </div>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}

// iso8601 -> "MMM D, HH:mm" (kisa, okunur). Cozulemezse ham deger.
function formatCreated(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
