"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChevronRight, Clock, Plus, Settings2 } from "lucide-react";
import { NEW_REQUEST_HREF, comingSoonMenu, isHere, primaryMenu, settingsMenu, STAFF_PERSONAL, type MenuLink } from "@/lib/menu";
import { useShell } from "./shell-context";
import { useBareShell } from "./sign-in";
import { cn } from "@/lib/cn";

/*
 * Rows keep their icon at a fixed x (centred in the 64px rail), so collapsing
 * only shrinks the width and cross-fades the labels; nothing re-mounts.
 */
const ROW = "relative flex h-11 w-full items-center gap-3 rounded-[var(--radius-ctl)] px-[11px] text-[14.5px] transition-colors duration-150";
const ROW_IDLE = "font-medium text-ink-2 hover:bg-hover hover:text-ink";
const ROW_CURRENT = "bg-sheet font-bold text-ink shadow-[0_0_0_1px_var(--color-line)]";

function Fade({ collapsed, children, className }: { collapsed: boolean; children: React.ReactNode; className?: string }) {
  return (
    <span
      aria-hidden={collapsed || undefined}
      className={cn(
        "min-w-0 whitespace-nowrap transition-opacity duration-200 ease-[var(--ease-out-expo)]",
        collapsed ? "pointer-events-none opacity-0" : "opacity-100 delay-75",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Sidebar() {
  const { session, collapsed } = useShell();
  if (useBareShell()) return null;
  return (
    <aside
      aria-label="Primary"
      className={cn(
        "sticky top-[var(--topbar-h)] hidden h-[calc(100dvh-var(--topbar-h))] shrink-0 flex-col overflow-hidden border-r border-line bg-rail lg:flex",
        "transition-[width] duration-200 ease-[var(--ease-out-expo)]",
        collapsed ? "w-16" : "w-[252px]",
      )}
    >
      {session === null ? <SidebarSkeleton collapsed={collapsed} /> : <Nav collapsed={collapsed} />}
    </aside>
  );
}

function SidebarSkeleton({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex flex-col gap-2 px-3 py-4" aria-hidden="true">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="flex h-11 items-center gap-3 px-[11px]">
          <div className="size-5 shrink-0 rounded-[5px] bg-line" />
          {!collapsed && <div className="h-2.5 rounded-full bg-line" style={{ width: `${44 + ((i * 37) % 36)}%` }} />}
        </div>
      ))}
    </div>
  );
}

function Nav({ collapsed }: { collapsed: boolean }) {
  const { session, me } = useShell();
  const pathname = usePathname();
  const role = session!.role;
  const primary = primaryMenu(role, session!.approver);
  const personal = role === "employee" ? [] : STAFF_PERSONAL;
  const settings = settingsMenu(role);
  const later = comingSoonMenu(role);
  const all = [...primary, ...personal, ...settings, ...later];
  const badge = (l: MenuLink) => (l.badge === "inbox" ? me?.inbox_count : l.badge === "unread" ? me?.unread_notifications : undefined);

  return (
    <nav className="no-scrollbar flex flex-1 flex-col overflow-y-auto overflow-x-hidden px-3 py-4 [&>*]:shrink-0" aria-label="Main">
      <Link
        href={NEW_REQUEST_HREF}
        title={collapsed ? "New request" : undefined}
        aria-label={collapsed ? "New request" : undefined}
        className={cn(
          "mb-4 flex h-11 items-center gap-3 rounded-[var(--radius-ctl)] bg-ink px-[11px] text-[14.5px] font-medium text-white transition-colors duration-150 hover:bg-ink-2",
        )}
      >
        <Plus className="size-5 shrink-0" strokeWidth={2} aria-hidden="true" />
        <Fade collapsed={collapsed}>New request</Fade>
      </Link>

      <ul className="flex flex-col gap-1">
        {primary
          .filter((l) => l.section !== "registers")
          .map((l) => (
            <li key={l.href}>
              <Row link={l} collapsed={collapsed} current={isHere(pathname, l, all)} count={badge(l)} />
            </li>
          ))}
        {personal.map((l) => (
          <li key={l.href}>
            <Row link={l} collapsed={collapsed} current={isHere(pathname, l, all)} />
          </li>
        ))}
      </ul>

      {primary.some((l) => l.section === "registers") && (
        <>
          <p className={cn("mb-1 mt-5 h-5 px-[11px] text-[12px] font-medium text-ink-3", collapsed && "mx-2 h-px bg-line p-0")} aria-hidden={collapsed || undefined}>
            {!collapsed && <Fade collapsed={collapsed}>Registers</Fade>}
          </p>
          <ul className="flex flex-col gap-1" aria-label="Registers">
            {primary
              .filter((l) => l.section === "registers")
              .map((l) => (
                <li key={l.href}>
                  <Row link={l} collapsed={collapsed} current={isHere(pathname, l, all)} />
                </li>
              ))}
          </ul>
        </>
      )}

      <div className="mt-auto flex flex-col gap-1 pt-6">
        {settings.length > 0 && <Fold label="Settings" icon={Settings2} links={settings} collapsed={collapsed} pathname={pathname} all={all} />}
        {later.length > 0 && <Fold label="Coming soon" icon={Clock} links={later} collapsed={collapsed} pathname={pathname} all={all} muted />}
      </div>
    </nav>
  );
}

function Row({ link, collapsed, current, count, small }: { link: MenuLink; collapsed: boolean; current: boolean; count?: number; small?: boolean }) {
  const Icon = link.icon;
  return (
    <Link
      href={link.href}
      title={collapsed ? link.label : undefined}
      aria-label={collapsed ? `${link.label}${count ? `, ${count}` : ""}` : undefined}
      aria-current={current ? "page" : undefined}
      className={cn(ROW, small && "h-10 text-[14px]", current ? ROW_CURRENT : ROW_IDLE)}
    >
      <Icon className={cn("shrink-0", small ? "size-[18px]" : "size-5")} strokeWidth={1.75} aria-hidden="true" />
      <Fade collapsed={collapsed} className="flex-1 truncate">
        {link.label}
      </Fade>
      {!!count && (
        <span
          className={cn(
            "tabular flex h-5 min-w-5 items-center justify-center rounded-full bg-ink px-1.5 text-[11px] font-bold text-white",
            collapsed && "absolute left-[30px] top-1 h-4 min-w-4 px-1 text-[10px] ring-2 ring-rail",
          )}
        >
          {count}
        </span>
      )}
      {current && !count && !collapsed && <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />}
    </Link>
  );
}

function Fold({
  label,
  icon: Icon,
  links,
  collapsed,
  pathname,
  all,
  muted,
}: {
  label: string;
  icon: typeof Clock;
  links: MenuLink[];
  collapsed: boolean;
  pathname: string;
  all: MenuLink[];
  muted?: boolean;
}) {
  const inside = links.some((l) => isHere(pathname, l, all));
  const [open, setOpen] = useState(inside);
  const [wasInside, setWasInside] = useState(inside);
  if (inside !== wasInside) {
    setWasInside(inside);
    if (inside) setOpen(true);
  }
  const show = open && !collapsed;
  const id = `fold-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={show}
        aria-controls={id}
        title={collapsed ? label : undefined}
        aria-label={collapsed ? label : undefined}
        className={cn(ROW, "h-10 text-[14px]", inside && !show ? "font-bold text-ink" : muted ? "font-medium text-ink-3 hover:bg-hover hover:text-ink" : ROW_IDLE)}
      >
        <Icon className="size-[18px] shrink-0" strokeWidth={1.75} aria-hidden="true" />
        <Fade collapsed={collapsed} className="flex-1 text-left">
          {label}
        </Fade>
        <Fade collapsed={collapsed}>
          <ChevronRight className={cn("size-4 transition-transform duration-200 ease-[var(--ease-out-expo)]", show && "rotate-90")} strokeWidth={1.75} aria-hidden="true" />
        </Fade>
      </button>
      <div id={id} className={cn("grid transition-[grid-template-rows,opacity] duration-200 ease-[var(--ease-out-expo)]", show ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")} inert={!show}>
        <ul className="flex min-w-[220px] flex-col gap-0.5 overflow-hidden pl-3">
          {links.map((l) => (
            <li key={l.href}>
              <Row link={l} collapsed={collapsed} current={isHere(pathname, l, all)} small />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
