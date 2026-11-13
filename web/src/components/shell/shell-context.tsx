"use client";

import { createContext, use, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { APPROVER_COOKIE, ROLE_COOKIE, USER_COOKIE, parseRole } from "@/lib/access";
import { api, invalidate, useApi, type ApiError, type Me } from "@/lib/api";
import { homeFor, type Role } from "@/lib/nav";

type Session = { role: Role; approver: boolean; user: string | null } | null;

type ShellState = {
  /** Navigation hints from cookies (null during SSR). The API re-checks everything server-side. */
  session: Session;
  /** The signed-in user as the API sees them. */
  me: Me | undefined;
  meError: ApiError | undefined;
  refreshMe: () => void;
  signInAs: (employeeNo: string, role: Role, approver: boolean) => void;
  /** Ends the server session (production) and clears the navigation cookies. */
  signOut: () => void;
  collapsed: boolean;
  toggleCollapsed: () => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
};

const ShellContext = createContext<ShellState | null>(null);

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

function readCookie(name: string) {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.split("=")[1];
}
function writeCookie(name: string, value: string) {
  const secure = location.protocol === "https:" ? "; secure" : "";
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax${secure}`;
}
function clearCookie(name: string) {
  document.cookie = `${name}=; path=/; max-age=0; samesite=lax`;
}

let cachedKey = "";
let cachedSession: Session = null;
function snapshot(): Session {
  const role = parseRole(readCookie(ROLE_COOKIE));
  const approver = readCookie(APPROVER_COOKIE) === "1";
  const user = readCookie(USER_COOKIE) ? decodeURIComponent(readCookie(USER_COOKIE)!) : null;
  const key = `${role}:${approver}:${user}`;
  if (key !== cachedKey) {
    cachedKey = key;
    cachedSession = { role, approver, user };
  }
  return cachedSession;
}

const COLLAPSE_KEY = "ea_rail_collapsed";

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSyncExternalStore(subscribe, snapshot, () => null);
  const collapsed = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(COLLAPSE_KEY) === "1",
    () => false,
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const meQuery = useApi<Me>(session?.user ? "/api/v1/me" : null);
  const me = session?.user ? meQuery.data : undefined;

  const signInAs = useCallback(
    (employeeNo: string, role: Role, approver: boolean) => {
      writeCookie(USER_COOKIE, employeeNo);
      writeCookie(ROLE_COOKIE, role);
      writeCookie(APPROVER_COOKIE, approver ? "1" : "0");
      notify();
      router.push(homeFor(role));
      router.refresh();
      invalidate();
    },
    [router],
  );

  const signOut = useCallback(() => {
    void api("/api/v1/auth/logout", { method: "POST" })
      .catch(() => undefined)
      .finally(() => {
        [USER_COOKIE, ROLE_COOKIE, APPROVER_COOKIE].forEach(clearCookie);
        notify();
        router.push("/");
        router.refresh();
        invalidate();
      });
  }, [router]);

  // Keep the navigation cookies in step with what the server says about this user.
  useEffect(() => {
    if (!me || !session) return;
    const approver = me.navigation.approval_inbox;
    if (me.role !== session.role || approver !== session.approver) {
      writeCookie(ROLE_COOKIE, me.role);
      writeCookie(APPROVER_COOKIE, approver ? "1" : "0");
      notify();
      router.refresh();
    }
  }, [me, session, router]);

  const toggleCollapsed = useCallback(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "0" : "1");
    notify();
  }, [collapsed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable=true]");
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(
    () => ({
      session,
      me,
      meError: session?.user ? meQuery.error : undefined,
      refreshMe: meQuery.reload,
      signInAs,
      signOut,
      collapsed,
      toggleCollapsed,
      paletteOpen,
      setPaletteOpen,
      menuOpen,
      setMenuOpen,
    }),
    [session, me, meQuery.error, meQuery.reload, signInAs, signOut, collapsed, toggleCollapsed, paletteOpen, menuOpen],
  );

  return <ShellContext value={value}>{children}</ShellContext>;
}

export function useShell() {
  const ctx = use(ShellContext);
  if (!ctx) throw new Error("useShell must be used inside ShellProvider");
  return ctx;
}
