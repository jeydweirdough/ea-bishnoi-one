/**
 * Task-first navigation. People navigate by what they do (requests, approvals,
 * tasks), not by the nine-group catalogue. Groups that are not built yet stay
 * reachable under one "Coming soon" fold, and move up here as they go live.
 */
import {
  Banknote,
  Building2,
  CarFront,
  ChartColumn,
  FileSignature,
  Gavel,
  Hourglass,
  Home,
  Inbox,
  ListChecks,
  ListTodo,
  Package,
  Plane,
  ScrollText,
  Stamp,
  Timer,
  Users,
  Bell,
  type LucideIcon,
} from "lucide-react";
import type { Role } from "./nav";

export type MenuLink = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Other path prefixes that count as "here". */
  match?: string[];
  badge?: "inbox" | "unread";
  /** "registers" groups record-keeping modules under their own heading. */
  section?: "registers";
};

export const NEW_REQUEST_HREF = "/me/new";

export function primaryMenu(role: Role, approver: boolean): MenuLink[] {
  const inbox: MenuLink[] = approver ? [{ href: "/inbox", label: "My approvals", icon: Gavel, badge: "inbox" }] : [];
  if (role === "employee") {
    return [
      { href: "/me", label: "Home", icon: Home },
      { href: "/me/requests", label: "My requests", icon: ListChecks, match: ["/r/", "/me/approvals-status", "/me/raise-concern", "/me/request-supplies", "/me/new"] },
      { href: "/me/assets", label: "My assets", icon: Package, match: ["/asset/"] },
      { href: "/me/travel", label: "My travel", icon: Plane },
      ...inbox,
      { href: "/me/notifications", label: "Notifications", icon: Bell, badge: "unread" },
    ];
  }
  return [
    { href: "/dashboard/executive-overview", label: "Home", icon: Home, match: ["/dashboard/priority-concerns", "/dashboard"] },
    { href: "/requests/all", label: "Requests", icon: Inbox, match: ["/requests", "/r/"] },
    { href: "/requests/approval-tracking", label: "In approval", icon: Hourglass, match: ["/dashboard/pending-approvals"] },
    { href: "/administration/tasks", label: "Tasks", icon: ListTodo },
    { href: "/administration/reports", label: "Reports", icon: ChartColumn },
    { href: "/assets/registry", label: "Assets", icon: Package, match: ["/assets", "/asset/", "/stock/"], section: "registers" },
    { href: "/fleet/vehicles", label: "Fleet", icon: CarFront, match: ["/fleet", "/vehicle/"], section: "registers" },
    { href: "/compliance/registrations", label: "Compliance", icon: Building2, match: ["/compliance", "/registration/", "/boc/"], section: "registers" },
    { href: "/travel/flights", label: "Travel", icon: Plane, match: ["/travel", "/flight/"], section: "registers" },
    { href: "/contracts/registry", label: "Contracts", icon: FileSignature, match: ["/contracts", "/contract/"], section: "registers" },
    { href: "/banking/corporate-cards", label: "Banking", icon: Banknote, match: ["/banking", "/bank-case/"], section: "registers" },
    ...inbox,
  ];
}

/** Personal links for staff, who also raise their own requests. */
export const STAFF_PERSONAL: MenuLink[] = [{ href: "/me/requests", label: "My own requests", icon: ListChecks, match: ["/me"] }];

export function settingsMenu(role: Role): MenuLink[] {
  if (role !== "admin") return [];
  return [
    { href: "/administration/approvals", label: "Approval routes", icon: Stamp },
    { href: "/administration/priorities-sla", label: "Deadlines (SLA)", icon: Timer },
    { href: "/administration/settings", label: "People & access", icon: Users },
    { href: "/administration/audit-logs", label: "Audit log", icon: ScrollText },
  ];
}

export function comingSoonMenu(role: Role): MenuLink[] {
  if (role === "employee") return [];
  return [
  ];
}

export function isHere(pathname: string, link: MenuLink, all: MenuLink[]): boolean {
  const prefixes = [link.href, ...(link.match ?? [])];
  const score = (l: MenuLink) =>
    Math.max(
      -1,
      ...[l.href, ...(l.match ?? [])].map((p) => (pathname === p || pathname.startsWith(p.endsWith("/") ? p : `${p}/`) ? p.length : -1)),
    );
  const mine = Math.max(-1, ...prefixes.map((p) => (pathname === p || pathname.startsWith(p.endsWith("/") ? p : `${p}/`) ? p.length : -1)));
  if (mine < 0) return false;
  // The most specific match wins, so "/requests/approval-tracking" lights "In approval", not "Requests".
  return all.every((other) => other === link || score(other) <= mine);
}
