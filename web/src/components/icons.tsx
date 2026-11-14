import {
  Link2,
  Wallet,
  Archive,
  ArrowLeftRight,
  BadgeCheck,
  Banknote,
  BedDouble,
  Bell,
  BookUser,
  Boxes,
  Building,
  Building2,
  CalendarClock,
  CalendarSync,
  CarFront,
  ChartColumn,
  CircleDot,
  ClipboardCheck,
  CreditCard,
  FilePlusCorner,
  FileQuestionMark,
  FileSignature,
  Files,
  FileText,
  Flag,
  FolderLock,
  Fuel,
  Gauge,
  Gavel,
  Globe,
  Hammer,
  HandCoins,
  Home,
  Hourglass,
  House,
  IdCard,
  Inbox,
  Landmark,
  LayoutDashboard,
  Library,
  ListChecks,
  ListTodo,
  MessageSquareWarning,
  Nfc,
  Package,
  PackagePlus,
  Plane,
  Receipt,
  RefreshCcw,
  Route,
  ScrollText,
  Settings,
  Settings2,
  ShieldCheck,
  Ship,
  ShoppingCart,
  Stamp,
  Store,
  Timer,
  UserCheck,
  Users,
  Warehouse,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { GroupIcon, SelfIcon } from "@/lib/nav";

export const GROUP_ICONS: Record<GroupIcon, LucideIcon> = {
  dashboard: LayoutDashboard,
  requests: Inbox,
  assets: Package,
  fleet: CarFront,
  compliance: Building2,
  travel: Plane,
  contracts: FileSignature,
  banking: Banknote,
  administration: Settings2,
};

export const SELF_ICONS: Record<SelfIcon, LucideIcon> = {
  home: Home,
  concern: MessageSquareWarning,
  supplies: PackagePlus,
  requests: ListChecks,
  status: CircleDot,
  bell: Bell,
};

/** One icon per module, keyed "group/item" — each picks the object the module is about. */
export const ITEM_ICONS: Record<string, LucideIcon> = {
  "dashboard/executive-overview": Gauge,
  "dashboard/pending-approvals": Hourglass,
  "dashboard/upcoming-renewals": CalendarClock,
  "dashboard/priority-concerns": Flag,

  "requests/all": ListTodo,
  "requests/from-link": Link2,
  "requests/asset-requests": ShoppingCart,
  "requests/local-purchase": Store,
  "requests/supplies": Boxes,
  "requests/repairs-maintenance": Wrench,
  "requests/department-concerns": MessageSquareWarning,
  "requests/other": FileQuestionMark,
  "requests/approval-tracking": Route,

  "assets/registry": Archive,
  "assets/assignment": UserCheck,
  "assets/transfers": ArrowLeftRight,
  "assets/repairs": Hammer,
  "assets/receiving-proof": ClipboardCheck,
  "assets/inventory": Warehouse,

  "fleet/vehicles": CarFront,
  "fleet/registration-insurance": ShieldCheck,
  "fleet/pms-repairs": Wrench,
  "fleet/fleet-cards": Fuel,
  "fleet/rfid": Nfc,
  "fleet/fuel-billing": Receipt,

  "compliance/registrations": Landmark,
  "compliance/sec-gis": FileText,
  "compliance/business-permits": BadgeCheck,
  "compliance/boc": Ship,
  "compliance/renewal-calendar": CalendarClock,
  "compliance/documents": FolderLock,

  "travel/flights": Plane,
  "travel/hotels": BedDouble,
  "travel/documents": BookUser,
  "travel/employee-visas": IdCard,
  "travel/expat-visas": Globe,
  "travel/renewals": BookUser,
  "travel/requirements": ListChecks,

  "contracts/lease": Building,
  "contracts/staff-house": House,
  "contracts/registry": Library,
  "contracts/renewals": RefreshCcw,
  "contracts/lessors": Users,
  "contracts/rent": Wallet,

  "banking/corporate-cards": CreditCard,
  "banking/card-renewals": CalendarSync,
  "banking/bank-requests": Files,
  "banking/account-applications": FilePlusCorner,
  "banking/documentation": Files,
  "banking/finance-coordination": HandCoins,

  "administration/tasks": ListTodo,
  "administration/approvals": Stamp,
  "administration/priorities-sla": Timer,
  "administration/reports": ChartColumn,
  "administration/audit-logs": ScrollText,
  "administration/settings": Settings,
};

const SELF_BY_SLUG: Record<string, LucideIcon> = {
  "": Home,
  "raise-concern": MessageSquareWarning,
  "request-supplies": PackagePlus,
  requests: ListChecks,
  "approvals-status": CircleDot,
  notifications: Bell,
};

/** Resolves the icon for any app route, so every list and header shares one icon per thing. */
export function iconForHref(href: string): LucideIcon {
  const [first = "", second] = href.split("/").filter(Boolean);
  if (first === "me") return SELF_BY_SLUG[second ?? ""] ?? Home;
  if (first === "inbox") return Gavel;
  if (second) return ITEM_ICONS[`${first}/${second}`] ?? CircleDot;
  return GROUP_ICONS[first as GroupIcon] ?? CircleDot;
}

/** The Executive Admin mark: an ink tile holding the accent ring — the app's one "live" symbol. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <rect width="32" height="32" rx="8" fill="#111111" />
      <circle cx="16" cy="16" r="7" fill="none" stroke="#A6C23F" strokeWidth="3" />
    </svg>
  );
}

/** Square icon tile used to lead headers and list rows. */
export function IconTile({ icon: Icon, size = "md" }: { icon: LucideIcon; size?: "sm" | "md" | "lg" }) {
  const box = size === "lg" ? "size-12 rounded-[12px]" : size === "md" ? "size-10 rounded-[10px]" : "size-8 rounded-[8px]";
  const glyph = size === "lg" ? "size-6" : size === "md" ? "size-5" : "size-4";
  return (
    <span className={`flex shrink-0 items-center justify-center border border-line bg-sheet text-ink ${box}`} aria-hidden="true">
      <Icon className={glyph} strokeWidth={1.6} />
    </span>
  );
}
