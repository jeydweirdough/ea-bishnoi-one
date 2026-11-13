"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LayoutGrid, Plus, X, type LucideIcon } from "lucide-react";
import { NEW_REQUEST_HREF, STAFF_PERSONAL, comingSoonMenu, isHere, primaryMenu, settingsMenu, type MenuLink } from "@/lib/menu";
import { cn } from "@/lib/cn";
import { useBareShell } from "./sign-in";
import { useShell } from "./shell-context";

type Tab = { link?: MenuLink; kind: "link" | "new" | "more" };

export function MobileTabBar() {
  const { session, me, menuOpen, setMenuOpen } = useShell();
  const pathname = usePathname();
  const bare = useBareShell();

  const primary = session ? primaryMenu(session.role, session.approver) : [];
  const staff = session && session.role !== "employee";
  const all = [...primary, ...(staff ? [...STAFF_PERSONAL, ...settingsMenu(session!.role), ...comingSoonMenu(session!.role)] : [])];
  const byHref = (h: string) => primary.find((l) => l.href === h);

  // Phones get at most five tabs; the center is always "New request".
  const tabs: Tab[] = !session
    ? []
    : staff
      ? [
          { kind: "link", link: byHref("/dashboard/executive-overview") },
          { kind: "link", link: byHref("/requests/all") },
          { kind: "new" },
          { kind: "link", link: byHref("/administration/tasks") },
          { kind: "more" },
        ]
      : session.approver
        ? [
            { kind: "link", link: byHref("/me") },
            { kind: "link", link: byHref("/me/requests") },
            { kind: "new" },
            { kind: "link", link: byHref("/inbox") },
            { kind: "link", link: byHref("/me/notifications") },
          ]
        : // Three tabs keep "+" centred; alerts already live on the top-bar bell.
          [{ kind: "link", link: byHref("/me") }, { kind: "new" }, { kind: "link", link: byHref("/me/requests") }];

  const linkHere = (l?: MenuLink) => Boolean(l && !menuOpen && isHere(pathname, l, all));
  const moreHere = menuOpen || (staff && !tabs.some((t) => linkHere(t.link)) && pathname !== NEW_REQUEST_HREF);
  const badge = (l?: MenuLink) => (l?.badge === "inbox" ? me?.inbox_count : l?.badge === "unread" ? me?.unread_notifications : undefined);

  if (bare) return null;
  return (
    <>
      <nav
        aria-label="Quick navigation"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-rail/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md supports-[backdrop-filter]:bg-rail/80 lg:hidden"
      >
        <ul className="mx-auto flex h-[var(--tabbar-h)] max-w-xl items-stretch px-1">
          {session === null
            ? Array.from({ length: 5 }, (_, i) => (
                <li key={i} className="flex flex-1 flex-col items-center justify-center gap-1.5" aria-hidden="true">
                  <span className="size-5 rounded-[5px] bg-line" />
                  <span className="h-2 w-10 rounded-full bg-line" />
                </li>
              ))
            : tabs.map((tab, i) => {
                if (tab.kind === "new") {
                  return (
                    <li key="new" className="flex flex-1 items-center justify-center">
                      <Link
                        href={NEW_REQUEST_HREF}
                        aria-label="New request"
                        aria-current={pathname === NEW_REQUEST_HREF ? "page" : undefined}
                        className="flex size-12 items-center justify-center rounded-full bg-ink text-white shadow-[0_6px_16px_-6px_rgb(17_17_17/0.45)] transition-transform duration-150 active:scale-95"
                      >
                        <Plus className="size-6" strokeWidth={2} />
                      </Link>
                    </li>
                  );
                }
                const active = tab.kind === "more" ? moreHere : linkHere(tab.link);
                const Icon: LucideIcon = tab.kind === "more" ? LayoutGrid : tab.link!.icon;
                const label = tab.kind === "more" ? "More" : tab.link!.label.replace("My requests", "Requests").replace("Notifications", "Alerts").replace("My approvals", "Approvals");
                const count = badge(tab.link);
                const inner = (
                  <>
                    <span className="relative">
                      <Icon className="size-[22px]" strokeWidth={active ? 2 : 1.6} />
                      {!!count && (
                        <span className="tabular absolute -right-2.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-ink px-1 text-[10px] font-bold text-white ring-2 ring-rail">
                          {count > 99 ? "99+" : count}
                        </span>
                      )}
                    </span>
                    <span className={cn("text-[11.5px] leading-none", active ? "font-bold text-ink" : "font-medium")}>{label}</span>
                  </>
                );
                const cls = cn(
                  "flex h-full w-full flex-col items-center justify-center gap-1.5 rounded-[var(--radius-ctl)] transition-colors duration-150",
                  active ? "text-ink" : "text-ink-3 active:bg-hover",
                );
                return (
                  <li key={tab.link?.href ?? `more-${i}`} className="flex flex-1">
                    {tab.kind === "more" ? (
                      <button type="button" className={cls} aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
                        {inner}
                      </button>
                    ) : (
                      <Link href={tab.link!.href} className={cls} aria-current={active ? "page" : undefined} aria-label={count ? `${label}, ${count}` : undefined}>
                        {inner}
                      </Link>
                    )}
                  </li>
                );
              })}
        </ul>
      </nav>
      <MenuSheet all={all} />
    </>
  );
}

function MenuSheet({ all }: { all: MenuLink[] }) {
  const { session, me, menuOpen, setMenuOpen } = useShell();
  const ref = useRef<HTMLDialogElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (menuOpen && !d.open) d.showModal();
    if (!menuOpen && d.open) d.close();
  }, [menuOpen]);

  const [prevPath, setPrevPath] = useState(pathname);
  if (prevPath !== pathname) {
    setPrevPath(pathname);
    if (menuOpen) setMenuOpen(false);
  }

  if (!session || session.role === "employee") return null;
  const tabbed = new Set(["/dashboard/executive-overview", "/requests/all", "/administration/tasks"]);
  const sections: { title?: string; links: MenuLink[]; muted?: boolean }[] = [
    { links: [...primaryMenu(session.role, session.approver).filter((l) => !tabbed.has(l.href)), ...STAFF_PERSONAL] },
    { title: "Settings", links: settingsMenu(session.role) },
    { title: "Coming soon", links: comingSoonMenu(session.role), muted: true },
  ];

  return (
    <dialog
      ref={ref}
      onClose={() => setMenuOpen(false)}
      onClick={(e) => e.target === e.currentTarget && setMenuOpen(false)}
      aria-label="More"
      className="fixed inset-0 m-0 mt-auto max-h-[88dvh] w-full max-w-none rounded-t-[16px] bg-canvas p-0 text-ink shadow-[var(--shadow-float)] backdrop:bg-ink/30 open:animate-[sheet-up_220ms_var(--ease-out-expo)] lg:hidden"
    >
      <div className="flex max-h-[88dvh] flex-col">
        <div className="relative flex shrink-0 items-center justify-between px-5 pb-2 pt-4">
          <div className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-edge" aria-hidden="true" />
          <h2 className="pt-2 text-[17px] font-bold">More</h2>
          <button type="button" onClick={() => setMenuOpen(false)} aria-label="Close" className="mt-1 flex size-11 items-center justify-center rounded-[var(--radius-ctl)] text-ink-2 hover:bg-hover">
            <X className="size-5" strokeWidth={1.75} />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain px-3 pb-[calc(20px+env(safe-area-inset-bottom))]">
          {sections
            .filter((s) => s.links.length)
            .map((s, i) => (
              <section key={i} className={cn(i > 0 && "mt-4 border-t border-line pt-3")}>
                {s.title && <h3 className="px-2 pb-1 text-[12.5px] font-medium text-ink-3">{s.title}</h3>}
                <ul className={cn(s.muted && "grid grid-cols-2")}>
                  {s.links.map((l) => {
                    const here = isHere(pathname, l, all);
                    const count = l.badge === "inbox" ? me?.inbox_count : undefined;
                    return (
                      <li key={l.href}>
                        <Link
                          href={l.href}
                          aria-current={here ? "page" : undefined}
                          className={cn(
                            "flex min-h-12 items-center gap-3 rounded-[var(--radius-ctl)] px-2 text-[15px]",
                            here ? "bg-sheet font-bold" : s.muted ? "text-ink-3" : "font-medium text-ink",
                          )}
                        >
                          <l.icon className={cn("shrink-0", s.muted ? "size-[18px]" : "size-5")} strokeWidth={1.75} aria-hidden="true" />
                          <span className="min-w-0 flex-1 truncate">{l.label}</span>
                          {!!count && <span className="tabular rounded-full bg-ink px-2 py-0.5 text-[11px] font-bold text-white">{count}</span>}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
        </div>
      </div>
    </dialog>
  );
}
