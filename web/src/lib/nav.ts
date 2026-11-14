/**
 * Single source of truth for Executive Admin navigation.
 * Every route, breadcrumb, search entry and Coming Soon page reads from here.
 * Content is taken from EXECUTIVE-ADMIN.md — nothing here is invented data.
 */

export type Role = "admin" | "assistant" | "employee";

export const BUILD_STEPS = [
  "Employee requests",
  "Approvals & administration",
  "Assets",
  "Fleet",
  "Compliance",
  "Travel & immigration",
  "Contracts & banking",
  "Import & export",
  "Documents & reports",
] as const;

export type Access = { admin: string; assistant: string; employee: string };

export type Workflow = "items" | "concerns";

export type NavItem = {
  slug: string;
  label: string;
  code: string;
  summary: string;
  /** 1-based index into BUILD_STEPS; null = not yet scheduled */
  step: number | null;
  fields?: string[];
  fieldsTitle?: string;
  workflows?: Workflow[];
  note?: string;
  access?: Access;
  /** Hidden from Assistants (configure policies, SLA and access) */
  adminOnly?: boolean;
  /**
   * A filtered view of another screen in the group (slug of that screen). It keeps its URL and
   * search entry, but is not listed as its own tab: the parent screen's filter chips reach it.
   */
  under?: string;
};

export type NavGroup = {
  slug: string;
  label: string;
  code: string;
  icon: GroupIcon;
  summary: string;
  access: Access;
  items: NavItem[];
};

export type GroupIcon =
  | "dashboard"
  | "requests"
  | "assets"
  | "fleet"
  | "compliance"
  | "travel"
  | "contracts"
  | "banking"
  | "administration";

/* ---------- shared field sets (EXECUTIVE-ADMIN.md › Key Records) ---------- */

const COMMON_REQUEST = [
  "Request ID",
  "Type",
  "Company",
  "Department",
  "Requester (employee ID)",
  "Assigned owner",
  "Priority — Low / Normal / High / Critical",
  "SLA / due date",
  "Current status",
  "Description",
  "Attachments",
  "Approval trail",
  "Activity history",
  "Timestamps",
];

const SUPPLY_LINES = [
  "Item name",
  "Specifications",
  "Quantity and unit",
  "Reason / purpose",
  "Existing asset ID (if replacing)",
  "Destination",
  "Receiving confirmation / proof",
  "Multiple line items (optional)",
];

const CONCERN_FIELDS = [
  "Concern type",
  "Location",
  "Affected asset (if any)",
  "Incident description",
  "Photos / evidence",
  "Impact",
  "Preferred contact",
  "Desired resolution date",
];

const ASSET = [
  "Serial number",
  "Brand and model",
  "Issued by / issued to",
  "Department",
  "Quantity (1 for a serialized asset)",
  "Purpose / description",
  "Condition — Brand New / Used / For Repair",
  "Proof of receiving",
  "Assignment history",
  "Repair history",
];

const VEHICLE = [
  "Plate number (optional)",
  "Conduction sticker",
  "Make, model and type",
  "Year model",
  "Color",
  "Owner",
  "Registration renewal date",
  "Insurance date",
  "PMS date",
  "Shell fleet card",
  "RFID",
  "Repair / parts history",
];

const GOV_REG = [
  "Document name",
  "Registration type — BOC / SEC / GIS / Business Permit / Pest Control / Fire Extinguisher",
  "Registration number",
  "Company",
  "Registration date",
  "Years of validity",
  "Explicit due date",
  "Attachments",
  "Status — Ongoing / Completed / For Renewal / Terminated or Void",
  "Notes",
  "Renewal history",
];

const CONTRACT = [
  "Lease category — office / staff house",
  "Company",
  "Coverage dates / year",
  "Due date",
  "Status",
  "Monthly rent",
  "Lessor name",
  "Site",
  "Documents",
  "Renewal history",
];

const FLIGHT = [
  "Booking reference number",
  "Employee / passenger",
  "Travel dates",
  "Local or international",
  "Valid ID with birth date (local) or passport (international)",
  "Attachments",
  "Approval / status",
];

const CARD = [
  "Masked card reference",
  "Issuer",
  "Custodian",
  "Expiration / renewal",
  "Document status",
  "Finance handoff",
];

const EMPLOYEE_COMMON = [
  "Request ID (generated)",
  "Employee ID and name (from People)",
  "Company and department",
  "Reporting head (prefilled)",
  "Request type and category",
  "Title",
  "Detailed concern / purpose",
  "Priority requested",
  "Location",
  "Needed-by date",
  "Attachments",
  "Submission date and status",
];

/* ---------- access templates (EXECUTIVE-ADMIN.md › User Types) ---------- */

const REGISTRY_ACCESS: Access = {
  admin: "Authorized companies",
  assistant: "Assigned scope",
  employee: "No access",
};

const REQUEST_ACCESS: Access = {
  admin: "Authorized company scope",
  assistant: "Assigned scope",
  employee: "Own requests only, through self-service",
};

/* ---------- the nine operational groups ---------- */

export const GROUPS: NavGroup[] = [
  {
    slug: "dashboard",
    label: "Dashboard",
    code: "EA-01",
    icon: "dashboard",
    summary: "Operational overview of approvals, renewals and priority concerns across authorized companies.",
    access: {
      admin: "Operational overview, authorized companies",
      assistant: "Assigned workload",
      employee: "Own requests, through My Dashboard",
    },
    items: [
      {
        slug: "executive-overview",
        label: "Executive Overview",
        code: "EA-01.1",
        summary: "One view of open requests, approvals, renewals and concerns for the companies you're authorized to see.",
        step: 9,
      },
      {
        slug: "pending-approvals",
        label: "Pending Approvals",
        code: "EA-01.2",
        summary: "Requests waiting at an approval stage, with the current approver and time in stage.",
        step: 2,
        workflows: ["items", "concerns"],
      },
      {
        slug: "upcoming-renewals",
        label: "Upcoming Renewals",
        code: "EA-01.3",
        summary: "Permits, registrations, visas, insurance, cards and leases nearing their due dates.",
        step: 5,
      },
      {
        slug: "priority-concerns",
        label: "Priority Concerns",
        code: "EA-01.4",
        summary: "High and Critical concerns ranked by effective priority and SLA.",
        step: 2,
      },
    ],
  },
  {
    slug: "requests",
    label: "Requests & Concerns",
    code: "EA-02",
    icon: "requests",
    summary: "Every request from submission through approval to fulfillment. Procurement lives here too.",
    access: REQUEST_ACCESS,
    items: [
      {
        slug: "all",
        label: "All Requests",
        code: "EA-02.1",
        summary: "Every request and concern in your scope, filterable by type, status, priority and owner.",
        step: 1,
        fields: COMMON_REQUEST,
        fieldsTitle: "Common request record",
      },
      {
        slug: "from-link",
        label: "From the Request Link",
        code: "EA-02.8",
        summary: "Requests sent through the shared link (/request) by people who weren't signed in. Check who sent it, then accept it into the approval route or decline it.",
        step: 1,
        fields: ["Name", "Work email", "Mobile", "Company / department", "Position", "Problem report", "Items requested", "Photos", "Urgent"],
        fieldsTitle: "What the link asks for",
        workflows: ["items", "concerns"],
        note: "Signed-in people who use the link skip this step: their requests are filed straight away.",
      },
      {
        slug: "asset-requests",
        label: "Asset Requests & Purchases",
        code: "EA-02.2",
        summary: "Asset orders and Purchase Order tracking. Arrivals are received here and linked to Asset Management.",
        step: 1,
        fields: SUPPLY_LINES,
        fieldsTitle: "Item lines",
        workflows: ["items"],
        note: "Requestors cannot create Purchase Orders or approve purchases.",
      },
      {
        slug: "local-purchase",
        label: "Local Purchase Requests",
        code: "EA-02.3",
        summary: "Approved local purchases for office use, such as chairs and tables.",
        step: 1,
        fields: SUPPLY_LINES,
        fieldsTitle: "Item lines",
        workflows: ["items"],
      },
      {
        slug: "supplies",
        label: "Office & Utility Supplies",
        code: "EA-02.4",
        summary: "Office and utility supply requests, from request to issuance.",
        step: 1,
        fields: SUPPLY_LINES,
        fieldsTitle: "Item lines",
        workflows: ["items"],
      },
      {
        slug: "repairs-maintenance",
        label: "Repairs & Maintenance",
        code: "EA-02.5",
        summary: "Equipment faults and facility repairs, from report to resolution.",
        step: 1,
        fields: CONCERN_FIELDS,
        fieldsTitle: "Concern details",
        workflows: ["concerns"],
      },
      {
        slug: "department-concerns",
        label: "Department Concerns",
        code: "EA-02.6",
        summary: "Workplace and interdepartmental concerns raised by staff.",
        step: 1,
        fields: CONCERN_FIELDS,
        fieldsTitle: "Concern details",
        workflows: ["concerns"],
        note: "Staff-selected urgency is a request. Admin sets the effective priority according to policy.",
      },
      {
        slug: "other",
        label: "Other Requests",
        code: "EA-02.7",
        summary: "Requests that don't fit another category, routed by category policy.",
        step: 1,
        fields: COMMON_REQUEST,
        fieldsTitle: "Common request record",
      },
      {
        slug: "approval-tracking",
        label: "Approval Tracking",
        code: "EA-02.8",
        summary: "Where every request sits in its approval chain: stage, approver, decision and comments.",
        step: 2,
        workflows: ["items", "concerns"],
        note: "Supports reject with reason, return for correction, resubmit, withdraw, escalate and delegate. Every action is audited.",
      },
    ],
  },
  {
    slug: "assets",
    label: "Asset Management",
    code: "EA-03",
    icon: "assets",
    summary: "The registry of company assets: who holds them, where they move, and their repair history.",
    access: REGISTRY_ACCESS,
    items: [
      { slug: "registry", label: "Asset Registry", code: "EA-03.1", summary: "Every company asset with its serial, condition and holder. Issue, transfer and repair from the asset itself.", step: 3, fields: ASSET, fieldsTitle: "Asset record" },
      { slug: "assignment", label: "Asset Assignment", code: "EA-03.2", summary: "Issue assets to employees and departments, with acknowledgement.", step: 3, under: "registry", fields: ["Asset", "Issued by", "Issued to", "Department", "Date issued", "Condition at issue", "Acknowledgement"], fieldsTitle: "Assignment record" },
      { slug: "repairs", label: "Repairs", code: "EA-03.4", summary: "The repair history of each asset, linked to Repairs & Maintenance requests.", step: 3, under: "registry" },
      { slug: "receiving-proof", label: "Receiving Proof", code: "EA-03.5", summary: "Proof of receiving for delivered items, linked to their request and the asset issued.", step: 3 },
      {
        slug: "inventory",
        label: "Consumables & Stock",
        code: "EA-03.6",
        summary: "Consumables, supplies and spare equipment counted by quantity, with every movement recorded, reorder alerts and counts.",
        step: 3,
        fields: ["Item code (automatic)", "Item name", "Category — Equipment / Supplies / Spare Parts / Consumables", "Brand / model", "Unit", "Storage location", "Quantity on hand", "Reserved / available", "Reorder level and quantity", "Unit cost (PHP)", "Preferred supplier", "Serialized on issue", "Last counted date", "Status"],
        fieldsTitle: "Inventory item",
        note: "Added to the plan as Phase 2.3a. Stock moves in from Receiving Proof and out through approved supply requests.",
      },
    ],
  },
  {
    slug: "fleet",
    label: "Fleet & Vehicles",
    code: "EA-04",
    icon: "fleet",
    summary: "Company vehicles, their papers, maintenance, fuel cards and RFID. Payments stay with Finance.",
    access: REGISTRY_ACCESS,
    items: [
      { slug: "vehicles", label: "Vehicle Registry", code: "EA-04.1", summary: "Every company vehicle with its registration, insurance, PMS, fuel card and RFID on one page.", step: 4, fields: VEHICLE, fieldsTitle: "Vehicle record" },
      { slug: "registration-insurance", label: "Registration & Insurance", code: "EA-04.2", summary: "Track registration and insurance dates so neither lapses.", step: 4, under: "vehicles" },
      {
        slug: "fleet-cards",
        label: "Shell Fleet Cards",
        code: "EA-04.4",
        summary: "Fuel cards per vehicle, with configured amounts and monthly billing references.",
        step: 4,
        fields: ["Plate or conduction sticker", "Vehicle", "Fuel type", "Company — 2MG / Getmeds", "Configured amount (e.g. PHP 10,000)", "Card reference", "Finance monthly billing reference", "Reconciliation status"],
        fieldsTitle: "Fleet card record",
        note: "Finance owns monthly billing and reconciliation. Admin tracks status by reference.",
        under: "vehicles",
      },
      {
        slug: "rfid",
        label: "RFID Management",
        code: "EA-04.5",
        summary: "Toll RFID accounts per vehicle, with balance and renewal monitoring.",
        step: 4,
        fields: ["Vehicle", "Provider / account reference", "Payment request", "Finance payment state", "Balance / renewal monitoring"],
        fieldsTitle: "RFID record",
        under: "vehicles",
      },
      { slug: "fuel-billing", label: "Fuel & Toll Billing", code: "EA-04.6", summary: "Fleet card statements and RFID reloads handed to Finance, and the payment references Finance returns.", step: 4, note: "Finance/Books owns payments and ledger. This view never posts financial entries." },
    ],
  },
  {
    slug: "compliance",
    label: "Corporate Compliance",
    code: "EA-05",
    icon: "compliance",
    summary: "Government registrations, permits and filings, tracked through every renewal.",
    access: REGISTRY_ACCESS,
    items: [
      { slug: "registrations", label: "Government Registrations", code: "EA-05.1", summary: "Every registration, permit and filing (SEC, GIS, business permits and more), its validity and its due date.", step: 5, fields: GOV_REG, fieldsTitle: "Registration record" },
      { slug: "sec-gis", label: "SEC / GIS", code: "EA-05.2", summary: "SEC registrations and General Information Sheet filings.", step: 5, under: "registrations" },
      { slug: "business-permits", label: "Business Permits", code: "EA-05.3", summary: "Business permits per company and site, with renewal tracking.", step: 5, under: "registrations" },
      { slug: "boc", label: "BOC Import / Export", code: "EA-05.4", summary: "Bureau of Customs import and export registrations and filings.", step: 5 },
    ],
  },
  {
    slug: "travel",
    label: "Travel & Immigration",
    code: "EA-06",
    icon: "travel",
    summary: "Flights, hotels and visas for employees and expats. Identity documents are restricted.",
    access: {
      admin: "Explicitly authorized, audited",
      assistant: "Need-to-know, restricted",
      employee: "No access",
    },
    items: [
      { slug: "flights", label: "Flight Bookings", code: "EA-06.1", summary: "Local and international bookings with their approvals.", step: 6, fields: FLIGHT, fieldsTitle: "Flight record", note: "Access to identity documents is restricted and audited." },
      { slug: "hotels", label: "Hotel Reservations", code: "EA-06.2", summary: "Hotel bookings linked to trips and travelers.", step: 6 },
      { slug: "documents", label: "Passports & Visas", code: "EA-06.3", summary: "Passports and visas of employees and expats, with expiry reminders at 90, 30, 7 and 0 days.", step: 6 },
      { slug: "employee-visas", label: "Employee Visas", code: "EA-06.3", summary: "Visa applications and status for employees.", step: 6, under: "documents" },
      { slug: "expat-visas", label: "Expat Visas", code: "EA-06.4", summary: "Visa and permit tracking for expatriate staff.", step: 6, under: "documents" },
      { slug: "renewals", label: "Passport & Visa Renewals", code: "EA-06.5", summary: "Expiry tracking for passports and visas.", step: 6, under: "documents" },
      { slug: "requirements", label: "Travel Requirements", code: "EA-06.6", summary: "Document checklists per destination and travel type.", step: 6 },
    ],
  },
  {
    slug: "contracts",
    label: "Contracts",
    code: "EA-07",
    icon: "contracts",
    summary: "Office and staff-house leases: coverage, rent, lessors and renewals.",
    access: REGISTRY_ACCESS,
    items: [
      { slug: "lease", label: "Lease Contracts", code: "EA-07.1", summary: "Office lease contracts and their terms.", step: 7, fields: CONTRACT, fieldsTitle: "Contract record", under: "registry" },
      { slug: "staff-house", label: "Staff House Contracts", code: "EA-07.2", summary: "Staff-house leases and occupancy terms.", step: 7, fields: CONTRACT, fieldsTitle: "Contract record", under: "registry" },
      { slug: "registry", label: "Contract Registry", code: "EA-07.3", summary: "Every office and staff-house lease in one register, including the ones ending soon.", step: 7, note: "Contracts may own the legal source of truth. This register monitors lease tasks and expiry without duplicating it." },
      { slug: "renewals", label: "Renewals", code: "EA-07.4", summary: "Lease due dates and renewal follow-up.", step: 7, under: "registry" },
      { slug: "rent", label: "Monthly Rent", code: "EA-07.6", summary: "This month's rent for every active lease, handed off to Finance with the payment reference Finance returns.", step: 7, note: "Finance/Books owns payments. This view tracks hand-offs only." },
      { slug: "lessors", label: "Lessors", code: "EA-07.5", summary: "Lessor contacts and the sites they lease.", step: 7 },
    ],
  },
  {
    slug: "banking",
    label: "Banking & Cards",
    code: "EA-08",
    icon: "banking",
    summary: "Corporate cards, bank applications and documentation, coordinated with Finance.",
    access: {
      admin: "Explicitly authorized, audited",
      assistant: "Need-to-know, restricted",
      employee: "No access",
    },
    items: [
      { slug: "corporate-cards", label: "Corporate Cards", code: "EA-08.1", summary: "Corporate cards by custodian, with masked references only, including the ones expiring soon.", step: 7, fields: CARD, fieldsTitle: "Card record", note: "Never stores CVV, PIN, full card numbers or banking credentials." },
      { slug: "card-renewals", label: "Credit Card Renewals", code: "EA-08.2", summary: "Card expiry and renewal follow-up.", step: 7, under: "corporate-cards" },
      { slug: "bank-requests", label: "Bank Requests", code: "EA-08.3", summary: "Account applications, bank documentation and Finance coordination, each with its requirement checklist.", step: 7, note: "Finance/Books owns payments, statements and reconciliation." },
      { slug: "account-applications", label: "Bank Account Applications", code: "EA-08.3", summary: "Account opening requests and bank requirements.", step: 7, under: "bank-requests" },
      { slug: "documentation", label: "Bank Documentation", code: "EA-08.4", summary: "Document status for bank requirements.", step: 7, under: "bank-requests" },
      { slug: "finance-coordination", label: "Finance Coordination", code: "EA-08.5", summary: "Handoffs to Finance and the payment status they return.", step: 7, under: "bank-requests", note: "Finance/Books owns payments, statements and reconciliation." },
    ],
  },
  {
    slug: "administration",
    label: "Administration",
    code: "EA-09",
    icon: "administration",
    summary: "Tasks, approvals, SLA policy, reports and the audit trail.",
    access: {
      admin: "Authorized",
      assistant: "Assigned / delegated",
      employee: "No access",
    },
    items: [
      { slug: "tasks", label: "Tasks", code: "EA-09.1", summary: "Admin and Assistant tasks, assigned and prioritized.", step: 2 },
      { slug: "approvals", label: "Approvals", code: "EA-09.2", summary: "Approval chain templates, mapped to designated users and positions.", step: 2, workflows: ["items", "concerns"], note: "Approval power is granted separately. Admin is not automatically an approver." },
      { slug: "priorities-sla", label: "Priorities & SLA", code: "EA-09.3", summary: "Priority levels and SLA targets by request type.", step: 2, adminOnly: true, access: { admin: "Authorized only", assistant: "No access", employee: "No access" } },
      { slug: "reports", label: "Reports", code: "EA-09.4", summary: "Operational reports across requests, assets and renewals.", step: 9 },
      { slug: "audit-logs", label: "Audit Logs", code: "EA-09.5", summary: "Every request, edit, decision and attachment event.", step: 2 },
      { slug: "settings", label: "Settings", code: "EA-09.6", summary: "Who can sign in, their user type and company, and what each person may access.", step: 2, adminOnly: true, access: { admin: "Authorized only", assistant: "No access", employee: "No access" } },
    ],
  },
];

/* ---------- employee self-service ---------- */

export type SelfServiceItem = NavItem & { short: string; icon: SelfIcon };
export type SelfIcon = "home" | "concern" | "supplies" | "requests" | "status" | "bell";

export const SELF_SERVICE: SelfServiceItem[] = [
  {
    slug: "",
    label: "My Dashboard",
    short: "Home",
    icon: "home",
    code: "ES-1",
    summary: "Your submitted requests, anything waiting on you, recent updates and announcements.",
    step: 1,
  },
  {
    slug: "raise-concern",
    label: "Raise a Concern",
    short: "Concern",
    icon: "concern",
    code: "ES-2",
    summary: "Report a department concern, equipment fault, facilities or workplace issue. Not for emergencies.",
    step: 1,
    fields: [...EMPLOYEE_COMMON.slice(0, 6), ...CONCERN_FIELDS],
    fieldsTitle: "Concern form",
    workflows: ["concerns"],
  },
  {
    slug: "request-supplies",
    label: "Request Supplies",
    short: "Supplies",
    icon: "supplies",
    code: "ES-3",
    summary: "Request office or utility supplies, equipment or assets, or an approved local purchase.",
    step: 1,
    fields: [...EMPLOYEE_COMMON.slice(0, 6), ...SUPPLY_LINES, "Desired date"],
    fieldsTitle: "Supply request form",
    workflows: ["items"],
  },
  {
    slug: "requests",
    label: "My Requests",
    short: "Requests",
    icon: "requests",
    code: "ES-4",
    summary: "Drafts, submitted, in review, approved, rejected, in progress, fulfilled and closed. Only yours.",
    step: 1,
    fields: ["Draft", "Submitted", "In review", "Approved", "Rejected", "In progress", "Fulfilled", "Closed"],
    fieldsTitle: "Statuses you'll see",
    note: "You can edit a request while it's a draft or returned for revision, and withdraw it before fulfillment.",
  },
  {
    slug: "approvals-status",
    label: "Approvals & Status",
    short: "Status",
    icon: "status",
    code: "ES-5",
    summary: "A read-only timeline of approval steps, who has it now, and any clarification requested.",
    step: 1,
    workflows: ["items", "concerns"],
    note: "Internal notes stay hidden.",
  },
  {
    slug: "notifications",
    label: "Notifications",
    short: "Alerts",
    icon: "bell",
    code: "ES-6",
    summary: "Decisions, comments, status changes, fulfillment and delivery or collection instructions.",
    step: 1,
  },
];

export const INBOX: NavItem = {
  slug: "inbox",
  label: "Approval Inbox",
  code: "AP-1",
  summary: "Requests waiting for your decision under the approval duties granted to you.",
  step: 2,
  workflows: ["items", "concerns"],
  note: "Approval duties are granted separately from your user type and scoped to specific chains.",
};

export const WORKFLOWS: Record<Workflow, { title: string; steps: string[] }> = {
  items: {
    title: "Request items",
    steps: ["Requestor", "Approval Heads", "COO", "Sir Naresh", "Admin / Assistant fulfillment", "Issued & closed"],
  },
  concerns: {
    title: "Staff concerns",
    steps: ["Staff", "Department Head", "Jasmine", "Ma'am Mira", "Ma'am Malhou", "Admin resolution", "Closed"],
  },
};

/* ---------- helpers ---------- */

export const groupHref = (g: NavGroup) => `/${g.slug}`;
export const itemHref = (g: NavGroup, i: NavItem) => `/${g.slug}/${i.slug}`;
export const selfHref = (i: SelfServiceItem) => (i.slug ? `/me/${i.slug}` : "/me");

export function visibleItems(group: NavGroup, role: Role) {
  return group.items.filter((i) => !(i.adminOnly && role !== "admin"));
}

/** The screens listed in a module's sub-menu: filtered views (`under`) are reached from their parent. */
export function tabItems(group: NavGroup) {
  return group.items.filter((i) => !i.under);
}

export function findGroup(slug: string) {
  return GROUPS.find((g) => g.slug === slug);
}

export function findItem(groupSlug: string, itemSlug: string) {
  const group = findGroup(groupSlug);
  const item = group?.items.find((i) => i.slug === itemSlug);
  return group && item ? { group, item } : undefined;
}

export function homeFor(role: Role) {
  return role === "employee" ? "/me" : "/dashboard/executive-overview";
}

export type Crumb = { label: string; href?: string; code?: string };

export function crumbsFor(pathname: string): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "me") {
    const item = SELF_SERVICE.find((s) => s.slug === (parts[1] ?? ""));
    const base: Crumb = { label: "Self-service", href: "/me" };
    return item && item.slug ? [base, { label: item.label, code: item.code }] : [{ label: "Self-service", code: "ES-1" }];
  }
  if (parts[0] === "inbox") return [{ label: "Approval Inbox", code: INBOX.code }];
  const group = findGroup(parts[0] ?? "");
  if (!group) return [];
  if (!parts[1]) return [{ label: group.label, code: group.code }];
  const item = group.items.find((i) => i.slug === parts[1]);
  return [
    { label: group.label, href: groupHref(group) },
    ...(item ? [{ label: item.label, code: item.code }] : []),
  ];
}

export type SearchEntry = { label: string; code: string; href: string; context: string; summary: string };

export function searchIndex(role: Role, approver: boolean): SearchEntry[] {
  const self = SELF_SERVICE.map((s) => ({
    label: s.label,
    code: s.code,
    href: selfHref(s),
    context: "Self-service",
    summary: s.summary,
  }));
  const inbox = approver
    ? [{ label: INBOX.label, code: INBOX.code, href: "/inbox", context: "Approver", summary: INBOX.summary }]
    : [];
  if (role === "employee") return [...self, ...inbox];
  const ops = GROUPS.flatMap((g) => [
    { label: g.label, code: g.code, href: groupHref(g), context: "Group", summary: g.summary },
    ...visibleItems(g, role).map((i) => ({
      label: i.label,
      code: i.code,
      href: itemHref(g, i),
      context: g.label,
      summary: i.summary,
    })),
  ]);
  return [...ops, ...inbox, ...self];
}
