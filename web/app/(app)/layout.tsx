import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";

// (app) grubu: composer (/new) + session akisi (/sessions/[id]) sidebar kabuğuyla.
// Landing (/) bu kabuğu ALMAZ — (marketing) grubunda, root layout'a dogrudan oturur.
export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="h-svh overflow-hidden bg-background">
        <header className="flex h-12 shrink-0 items-center px-3">
          <SidebarTrigger className="text-muted-foreground" />
        </header>
        <div className="mx-auto flex w-full max-w-[720px] flex-1 flex-col overflow-hidden px-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
