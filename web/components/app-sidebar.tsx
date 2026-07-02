"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { listTasks, type TaskRecord } from "@/lib/api";
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
  const [tasks, setTasks] = useState<TaskRecord[]>([]);

  // Fetch on navigation only (no polling): pathname degisince bir kez cek.
  useEffect(() => {
    let active = true;
    listTasks().then((t) => {
      if (active) setTasks(t);
    });
    return () => {
      active = false;
    };
  }, [pathname]);

  return (
    <Sidebar>
      <SidebarHeader className="px-3 py-2 text-sm font-semibold">
        QuantumLabs
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Sessions</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {tasks.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  No sessions yet
                </div>
              )}
              {tasks.map((t) => {
                const created = createdFromSessionId(t.session_id);
                return (
                  <SidebarMenuItem key={t.id}>
                    <SidebarMenuButton
                      render={<Link href={`/sessions/${t.id}`} />}
                      isActive={pathname === `/sessions/${t.id}`}
                    >
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate text-sm">{t.id}</span>
                        {created && (
                          <span className="truncate text-xs text-muted-foreground">
                            {created}
                          </span>
                        )}
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}

// session_id formati: "YYYY-MM-DD_HHMMSS_<taskid>" -> okunur created string.
function createdFromSessionId(sid: string | undefined): string | null {
  if (!sid) return null;
  const m = sid.match(/^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!m) return sid;
  return `${m[1]} ${m[2]}:${m[3]}:${m[4]}`;
}
