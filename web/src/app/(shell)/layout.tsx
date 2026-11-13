import { AuthGate } from "@/components/shell/auth-gate";
import { CommandPalette } from "@/components/shell/command-palette";
import { MobileTabBar } from "@/components/shell/mobile-nav";
import { ShellProvider } from "@/components/shell/shell-context";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { ToastProvider } from "@/components/ui/feedback";

export default function ShellLayout({ children }: LayoutProps<"/">) {
  return (
    <ShellProvider>
      <ToastProvider>
        <a
          href="#main"
          className="fixed left-3 top-3 z-[60] -translate-y-20 rounded-[var(--radius-ctl)] bg-ink px-3 py-2 text-[14px] font-medium text-white focus-visible:translate-y-0"
        >
          Skip to content
        </a>
        <TopBar />
        <div className="flex">
          <Sidebar />
          <main id="main" className="min-w-0 flex-1 pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+16px)] lg:pb-12">
            <AuthGate>{children}</AuthGate>
          </main>
        </div>
        <MobileTabBar />
        <CommandPalette />
      </ToastProvider>
    </ShellProvider>
  );
}
