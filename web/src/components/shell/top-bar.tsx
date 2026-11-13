"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Bell, Check, KeyRound, LogOut, PanelLeftClose, PanelLeftOpen, Search, UserRound } from "lucide-react";
import { Mark } from "@/components/icons";
import { useApi } from "@/lib/api";
import { homeFor, type Role } from "@/lib/nav";
import { cn } from "@/lib/cn";
import { useShell } from "./shell-context";
import { ChangePasswordForm, useAuthMode, useBareShell } from "./sign-in";
import { Dialog, useToast } from "@/components/ui/feedback";

export function TopBar() {
  const { session, me, collapsed, toggleCollapsed, setPaletteOpen } = useShell();
  const bare = useBareShell();
  const home = session ? homeFor(session.role) : "/";
  if (bare)
    return (
      <header className="sticky top-0 z-40 flex h-[var(--topbar-h)] items-center border-b border-line bg-rail px-4 sm:px-6">
        <span className="flex items-center gap-2.5">
          <Mark size={28} />
          <span className="flex flex-col leading-none">
            <span className="text-[15px] font-bold tracking-[-0.01em]">Executive Admin</span>
            <span className="mt-1 text-[11.5px] font-medium text-ink-3">Bishnoi One · Corporate Services</span>
          </span>
        </span>
      </header>
    );
  return (
    <header className="sticky top-0 z-40 flex h-[var(--topbar-h)] items-center gap-2 border-b border-line bg-rail/90 px-3 backdrop-blur-md supports-[backdrop-filter]:bg-rail/80 sm:px-4 lg:gap-3">
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-pressed={collapsed}
        className="hidden size-9 items-center justify-center rounded-[var(--radius-ctl)] text-ink-2 transition-colors duration-150 hover:bg-hover hover:text-ink lg:flex"
      >
        {collapsed ? <PanelLeftOpen className="size-[18px]" strokeWidth={1.75} /> : <PanelLeftClose className="size-[18px]" strokeWidth={1.75} />}
      </button>

      <Link href={home} className="flex min-w-0 items-center gap-2.5 rounded-[var(--radius-ctl)] pr-2">
        <Mark size={28} />
        <span className="flex min-w-0 flex-col leading-none">
          <span className="truncate text-[15px] font-bold tracking-[-0.01em]">Executive Admin</span>
          <span className="mt-1 hidden text-[11.5px] font-medium text-ink-3 sm:block">Bishnoi One · Corporate Services</span>
        </span>
      </Link>

      <div className="flex flex-1 justify-center px-2">
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="hidden h-9 w-full max-w-[420px] items-center gap-2.5 rounded-[var(--radius-ctl)] border border-edge bg-sheet px-3 text-left text-[14px] text-ink-3 transition-colors duration-150 hover:border-mute hover:text-ink-2 md:flex"
        >
          <Search className="size-4 shrink-0" strokeWidth={1.75} />
          <span className="flex-1 truncate">Search modules or codes</span>
          <kbd className="tabular rounded-[5px] border border-line bg-canvas px-1.5 py-0.5 font-sans text-[11px] font-medium text-ink-3">
            <ShortcutLabel />
          </kbd>
        </button>
      </div>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        aria-label="Search modules"
        className="flex size-11 items-center justify-center rounded-[var(--radius-ctl)] text-ink-2 transition-colors duration-150 hover:bg-hover hover:text-ink md:hidden"
      >
        <Search className="size-5" strokeWidth={1.75} />
      </button>

      <Link
        href="/me/notifications"
        aria-label={me?.unread_notifications ? `Notifications, ${me.unread_notifications} unread` : "Notifications"}
        className="relative flex size-11 items-center justify-center rounded-[var(--radius-ctl)] text-ink-2 transition-colors duration-150 hover:bg-hover hover:text-ink md:size-9"
      >
        <Bell className="size-5 md:size-[18px]" strokeWidth={1.75} />
        {!!me?.unread_notifications && (
          <span className="tabular absolute right-1 top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-ink px-1 text-[10.5px] font-bold text-white ring-2 ring-rail md:-right-0.5 md:-top-0.5">
            {me.unread_notifications > 99 ? "99+" : me.unread_notifications}
          </span>
        )}
      </Link>

      <AccountMenu />
    </header>
  );
}

const noop = () => () => {};
function ShortcutLabel() {
  const apple = useSyncExternalStore(
    noop,
    () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent),
    () => false,
  );
  return <>{apple ? "⌘K" : "Ctrl K"}</>;
}

type DevUser = { employee_no: string; name: string; designation: string | null; role: Role; approver: boolean; company: string };

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", assistant: "Assistant", employee: "Employee" };

function initials(name?: string) {
  if (!name) return "";
  const parts = name.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

function AccountMenu() {
  const { session, me, signInAs, signOut } = useShell();
  const mode = useAuthMode();
  const [open, setOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const toast = useToast();
  const ref = useRef<HTMLDivElement>(null);
  const users = useApi<DevUser[]>(open && mode === "dev" ? "/api/v1/dev/users" : null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = me?.employee.name;
  const roleLabel = me ? ROLE_LABEL[me.role] : undefined;

  // Production: nothing to show until someone has signed in (the sign-in form is the page itself).
  if (mode === "password" && !me) return null;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={name ? `Account: ${name}, ${roleLabel}` : "Sign in"}
        className="flex h-11 items-center gap-2 rounded-[var(--radius-ctl)] pl-1 pr-1 transition-colors duration-150 hover:bg-hover md:h-9 md:pr-2.5"
      >
        <span className="tabular flex size-8 items-center justify-center rounded-full bg-ink text-[11px] font-bold tracking-wide text-white md:size-7">
          {name ? initials(name) : <UserRound className="size-4" strokeWidth={1.75} aria-hidden="true" />}
        </span>
        <span className="hidden min-w-[4.5rem] max-w-[10rem] flex-col text-left leading-tight md:flex">
          <span className="truncate text-[13.5px] font-medium text-ink">{name ?? (session?.user ? " " : "Sign in")}</span>
          {roleLabel && <span className="text-[11.5px] text-ink-3">{roleLabel}</span>}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Account"
          className="rise-in absolute right-0 top-[calc(100%+8px)] z-50 flex max-h-[min(560px,calc(100dvh-80px))] w-[min(320px,calc(100vw-24px))] flex-col rounded-[var(--radius-panel)] border border-line bg-sheet shadow-[var(--shadow-float)]"
        >
          {me && (
            <div className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-3.5">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-[13px] font-bold text-white">{initials(me.employee.name)}</span>
              <span className="min-w-0">
                <span className="block truncate text-[14px] font-bold">{me.employee.name}</span>
                <span className="block truncate text-[12.5px] text-ink-3">
                  {roleLabel} · {me.employee.company.code}
                  {me.approver ? " · Approver" : ""}
                </span>
              </span>
            </div>
          )}
          {me?.navigation.approval_inbox && (
            <Link
              href="/inbox"
              onClick={() => setOpen(false)}
              className="mx-3 mt-3 flex h-10 shrink-0 items-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink pl-3 pr-3.5 text-[14px] font-medium text-white transition-opacity duration-150 hover:opacity-90"
            >
              <span className="size-3 rounded-full border-[2.5px] border-accent" aria-hidden="true" />
              <span className="flex-1">Open Approval Inbox</span>
              {me.inbox_count > 0 && <span className="tabular text-[12.5px] text-white/70">{me.inbox_count}</span>}
            </Link>
          )}
          {mode === "password" && (
            <div className="flex flex-col gap-0.5 p-2">
              {me?.email && <p className="truncate px-2 pb-1.5 pt-1 text-[12.5px] text-ink-3">{me.email}</p>}
              <button
                type="button"
                onClick={() => (setOpen(false), setChanging(true))}
                className="flex h-11 items-center gap-3 rounded-[var(--radius-ctl)] px-2 text-left text-[14px] font-medium hover:bg-canvas"
              >
                <KeyRound className="size-[18px] text-ink-2" strokeWidth={1.75} aria-hidden="true" /> Change password
              </button>
              <button type="button" onClick={signOut} className="flex h-11 items-center gap-3 rounded-[var(--radius-ctl)] px-2 text-left text-[14px] font-medium hover:bg-canvas">
                <LogOut className="size-[18px] text-ink-2" strokeWidth={1.75} aria-hidden="true" /> Sign out
              </button>
            </div>
          )}
          {mode === "dev" && (
          <>
          <div className="shrink-0 px-4 pb-1.5 pt-3">
            <p className="text-[13px] font-bold">Sign in as</p>
            <p className="mt-0.5 text-[12px] leading-snug text-ink-3">Development directory. In production, sign-in comes from One Admin.</p>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {users.data?.map((u) => {
              const current = u.employee_no === session?.user;
              return (
                <li key={u.employee_no}>
                  <button
                    type="button"
                    aria-current={current || undefined}
                    onClick={() => {
                      setOpen(false);
                      if (!current) signInAs(u.employee_no, u.role, u.approver);
                    }}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-[var(--radius-ctl)] px-2 py-2 text-left transition-colors duration-150",
                      current ? "bg-canvas" : "hover:bg-canvas",
                    )}
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-line bg-sheet text-[11px] font-bold text-ink-2">
                      {initials(u.name)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium">{u.name}</span>
                      <span className="block truncate text-[12px] text-ink-3">
                        {ROLE_LABEL[u.role]}
                        {u.approver ? " · Approver" : ""} · {u.designation}
                      </span>
                    </span>
                    {current && <Check className="size-4 shrink-0" strokeWidth={2} aria-label="Signed in" />}
                  </button>
                </li>
              );
            })}
            {users.loading && !users.data && <li className="px-2 py-3 text-[13px] text-ink-3">Loading people…</li>}
            {users.error && <li className="px-2 py-3 text-[13px] text-danger">The API is not reachable. Start it on port 8000.</li>}
          </ul>
          </>
          )}
        </div>
      )}
      <Dialog open={changing} onClose={() => setChanging(false)} title="Change password" description="Other devices where you are signed in will be signed out.">
        <ChangePasswordForm
          onDone={() => {
            setChanging(false);
            toast("Password changed");
          }}
        />
      </Dialog>
    </div>
  );
}
