"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Ban,
  CalendarClock,
  CarFront,
  Check,
  ChevronRight,
  CircleCheck,
  FileText,
  Landmark,
  ListTodo,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCcw,
  Search,
  Ship,
  TriangleAlert,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { api, fmtDate, fmtRelative, invalidate, post, qs, useApi, type Attachment, type Page, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Chip, Input } from "@/components/ui/controls";
import { CountStrip, EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { RecordAttachments } from "@/components/assets/assets";
import { DueLabel, peso } from "@/components/fleet/fleet";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { useShell } from "@/components/shell/shell-context";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- types */

type Reg = {
  id: number;
  reference: string;
  company: { id: number; code: string; name: string };
  document_name: string;
  registration_type: string;
  registration_number: string | null;
  registration_date: string | null;
  validity_years: number | null;
  expiry_date: string | null;
  due_date: string | null;
  days_left: number | null;
  responsible: Person | null;
  status: "ongoing" | "for_renewal" | "completed" | "expired" | "terminated" | "void";
  site: string | null;
  notes: string | null;
  version: number;
};
type RegDetail = Reg & {
  renewals: { id: number; previous_expiry: string | null; registration_date: string; new_expiry: string; registration_number: string | null; cost_php: string | null; notes: string | null; filed_by: Person; at: string }[];
  attachments: Attachment[];
  tasks: { id: number; reference: string; title: string; status: string; due_date: string | null; assignee: Person | null }[];
};
type Boc = {
  id: number;
  reference: string;
  direction: "import" | "export";
  shipment_reference: string | null;
  bill_of_lading: string | null;
  entry_number: string | null;
  description: string;
  counterparty: string | null;
  origin: string | null;
  destination: string | null;
  eta: string | null;
  broker: string | null;
  officer: Person | null;
  status: string;
  updated_at: string;
};
type BocDetail = Boc & { events: { id: number; milestone: string | null; note: string | null; actor: Person; at: string }[]; attachments: Attachment[]; next: string[] };

const TYPES = ["Bureau of Customs", "SEC", "GIS", "Business Permit", "Pest Control", "Fire Extinguishers", "Other"];
const STATUS_LABEL: Record<Reg["status"], string> = { ongoing: "Ongoing", for_renewal: "For renewal", completed: "Completed", expired: "Expired", terminated: "Terminated", void: "Void" };
const MILESTONE_LABEL: Record<string, string> = { draft: "Draft", lodged: "Lodged", assessment: "Assessment", duties_paid: "Duties paid", released: "Released", delivered: "Delivered", closed: "Closed", cancelled: "Cancelled" };
const MILESTONES = ["draft", "lodged", "assessment", "duties_paid", "released", "delivered", "closed"];

function RegStatus({ s }: { s: Reg["status"] }) {
  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border pl-2 pr-2.5 text-[12.5px] font-medium whitespace-nowrap",
        s === "expired" ? "border-danger/30 bg-danger-soft text-danger" : s === "for_renewal" ? "border-ink bg-sheet" : ["terminated", "void", "completed"].includes(s) ? "border-line bg-canvas text-ink-3" : "border-edge bg-sheet",
      )}
    >
      {s === "for_renewal" ? <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" /> : s === "expired" ? <TriangleAlert className="size-3.5" strokeWidth={2} aria-hidden="true" /> : <CircleCheck className="size-3.5" strokeWidth={2} aria-hidden="true" />}
      {STATUS_LABEL[s]}
    </span>
  );
}

const REG_FIELDS: FieldDef[] = [
  { name: "document_name", label: "Document", required: true, placeholder: "e.g. Mayor's Permit — Makati HQ" },
  { name: "registration_type", label: "Type", type: "select", options: TYPES, required: true, half: true },
  { name: "registration_number", label: "Registration number", half: true },
  { name: "registration_date", label: "Registered on", type: "date", half: true },
  { name: "validity_years", label: "Valid for (years)", type: "number", half: true, hint: "Fills in the expiry date" },
  { name: "expiry_date", label: "Expires on", type: "date", half: true },
  { name: "due_date", label: "Filing due date", type: "date", half: true, hint: "When the renewal must be filed" },
  { name: "responsible_id", label: "Responsible", type: "person", more: true, half: true },
  { name: "site", label: "Site / branch", more: true, half: true },
  { name: "notes", label: "Notes", type: "textarea", more: true },
];

function useDebounced(v: string) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), 250);
    return () => clearTimeout(t);
  }, [v]);
  return d;
}

/* ---------------------------------------------------------------- registrations (all / SEC-GIS / permits) */

const KINDS: { value: "all" | "sec-gis" | "business-permits"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "sec-gis", label: "SEC / GIS" },
  { value: "business-permits", label: "Business permits" },
];

/** The one register of registrations, permits and filings. SEC/GIS and business permits are type filters, not separate screens. */
export function RegistrationsPage({ kind = "all" }: { kind?: "all" | "sec-gis" | "business-permits" }) {
  const toast = useToast();
  const [group, setGroup] = useState(kind);
  const defaultType = group === "sec-gis" ? "SEC" : "Business Permit";
  const [q, setQ] = useState("");
  const term = useDebounced(q);
  const [status, setStatus] = useState<string | undefined>();
  const [creating, setCreating] = useState(false);
  const data = useApi<Page<Reg> & { summary: Record<string, number> }>(`/api/v1/compliance/registrations${qs({ group, q: term, status: status ? [status] : undefined, page_size: 100 })}`);
  const s = data.data?.summary;
  return (
    <ModuleShell
      group="compliance"
      item="registrations"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Add registration
          </Button>
          <DataTools dataset="registrations" statuses={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))} />
        </>
      }
    >
        <div className="mb-5">
          <CountStrip
            items={[
              { icon: RefreshCcw, label: "For renewal", value: s?.for_renewal, href: "/dashboard/upcoming-renewals" },
              { icon: TriangleAlert, label: "Expired", value: s?.expired, href: "/compliance/registrations", danger: true },
              { icon: CircleCheck, label: "Ongoing", value: s?.ongoing, href: "/compliance/registrations" },
              { icon: FileText, label: "Completed", value: s?.completed, href: "/compliance/registrations" },
            ]}
          />
        </div>
      <Panel>
        <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
          <label className="relative block">
            <span className="sr-only">Search registrations</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
            <Input type="search" placeholder="Search document or number" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0" role="group" aria-label="Type">
            {KINDS.map((k) => (
              <Chip key={k.value} on={group === k.value} onClick={() => setGroup(k.value)}>
                {k.label}
              </Chip>
            ))}
          </div>
          <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0" role="group" aria-label="Status">
            {[undefined, "for_renewal", "expired", "ongoing", "completed"].map((v) => (
              <Chip key={v ?? "all"} on={status === v} onClick={() => setStatus(v)}>
                {v ? STATUS_LABEL[v as Reg["status"]] : "All"}
              </Chip>
            ))}
          </div>
        </div>
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState icon={Landmark} title={q || status ? "No matching records" : "No registrations yet"} body={q || status ? undefined : "Add permits, SEC, GIS, BOC and other registrations to get reminders before they lapse."} compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((r) => (
              <li key={r.id}>
                <Link href={`/registration/${r.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
                  <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line sm:mt-0" aria-hidden="true">
                    <Landmark className="size-5" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-bold">{r.document_name}</span>
                    <span className="block text-[12.5px] text-ink-3">
                      {r.registration_type}
                      {r.registration_number ? ` · ${r.registration_number}` : ""}
                      {r.responsible ? ` · ${r.responsible.name}` : ""}
                    </span>
                    <span className="mt-1 block text-[12.5px] sm:hidden">
                      <DueLabel days={r.days_left} label={r.due_date ? "Filing" : "Expiry"} />
                    </span>
                  </span>
                  <span className="hidden shrink-0 flex-col items-end gap-1 text-[12.5px] sm:flex">
                    <RegStatus s={r.status} />
                    {["ongoing", "for_renewal", "expired"].includes(r.status) && <DueLabel days={r.days_left} label={r.due_date ? "Filing" : "Expiry"} />}
                  </span>
                  <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a registration"
        fields={REG_FIELDS}
        initial={{ registration_type: defaultType }}
        submitLabel="Add"
        scan={{ kind: "registration", attachTo: "registration" }}
        onSubmit={async (p) => {
          const r = await post<Reg>("/api/v1/compliance/registrations", p);
          toast(`Added · ${r.reference}`);
          invalidate();
          return r;
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- registration page */

export function RegistrationDetailView({ id }: { id: number }) {
  const toast = useToast();
  const { me } = useShell();
  const q = useApi<RegDetail>(`/api/v1/compliance/registrations/${id}`);
  const [dialog, setDialog] = useState<null | "edit" | "renew" | "assign" | "completed" | "terminated" | "void">(null);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This registration doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const r = q.data;
  if (!r) return <PageFrame><SkeletonRows /></PageFrame>;
  const open = ["ongoing", "for_renewal", "expired"].includes(r.status);
  const closeFields: FieldDef[] = [{ name: "reason", label: "Reason", type: "textarea", required: true }];
  const dialogs = {
    edit: { title: "Edit registration", fields: REG_FIELDS, initial: fromRecord(REG_FIELDS, { ...r, responsible_id: r.responsible?.id } as unknown as Record<string, unknown>), url: `/api/v1/compliance/registrations/${r.id}`, method: "PATCH", extra: { version: r.version }, done: "Saved" },
    renew: {
      title: "Record renewal",
      fields: [
        { name: "registration_date", label: "Renewed on", type: "date", required: true, half: true },
        { name: "validity_years", label: "Valid for (years)", type: "number", half: true },
        { name: "expiry_date", label: "New expiry", type: "date", half: true, hint: "Or leave empty to use the years" },
        { name: "due_date", label: "Next filing due", type: "date", half: true },
        { name: "registration_number", label: "New registration number", half: true },
        { name: "cost_php", label: "Fees paid", type: "money", half: true },
        { name: "notes", label: "Notes", type: "textarea", more: true },
      ] as FieldDef[],
      initial: { registration_date: new Date().toISOString().slice(0, 10), validity_years: r.validity_years ? String(r.validity_years) : "" },
      url: `/api/v1/compliance/registrations/${r.id}/renew`,
      done: "Renewal recorded",
    },
    assign: {
      title: "Assign the renewal",
      fields: [
        { name: "assignee_id", label: "Who files it?", type: "person", required: true, placeholder: "Choose a person" },
        { name: "due_date", label: "Task due", type: "date", half: true, hint: "Defaults to the filing due date" },
        { name: "note", label: "Note", type: "textarea", more: true },
      ] as FieldDef[],
      url: `/api/v1/compliance/registrations/${r.id}/assign-renewal`,
      done: "Renewal assigned",
    },
    completed: { title: "Mark completed", fields: closeFields, url: `/api/v1/compliance/registrations/${r.id}/status`, extra: { status: "completed" }, done: "Marked completed" },
    terminated: { title: "Terminate registration", fields: closeFields, url: `/api/v1/compliance/registrations/${r.id}/status`, extra: { status: "terminated" }, done: "Terminated" },
    void: { title: "Void this record", fields: closeFields, url: `/api/v1/compliance/registrations/${r.id}/status`, extra: { status: "void" }, done: "Voided" },
  } as const;
  const spec = dialog ? dialogs[dialog] : undefined;

  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Corporate Compliance", href: "/compliance/registrations" }, { label: r.reference }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Landmark className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {r.reference} · {r.registration_type}
            {r.registration_number ? ` · ${r.registration_number}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] text-balance sm:text-[30px]">{r.document_name}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <RegStatus s={r.status} />
            <span className="text-[13px] text-ink-2">{r.responsible ? `Responsible: ${r.responsible.name}` : "No one responsible yet"}</span>
          </div>
        </div>
      </header>

      <ul className="mt-6 grid gap-3 sm:grid-cols-3">
        {[
          ["Filing due", r.due_date],
          ["Expires", r.expiry_date],
          ["Registered", r.registration_date],
        ].map(([label, date]) => {
          const days = date ? Math.round((new Date(`${date}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()) / 864e5) : null;
          return (
            <li key={label} className={cn("rounded-[var(--radius-panel)] border bg-sheet p-4", open && label !== "Registered" && days !== null && days <= 30 ? "border-ink" : "border-line")}>
              <p className="text-[13px] font-medium text-ink-3">{label}</p>
              <p className="mt-1 text-[16px] font-bold">{fmtDate(date)}</p>
              {label !== "Registered" && open && <p className="mt-0.5 text-[12.5px]"><DueLabel days={days} /></p>}
            </li>
          );
        })}
      </ul>

      {open && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="primary" icon={RefreshCcw} onClick={() => setDialog("renew")}>
            Record renewal
          </Button>
          <Button icon={UserPlus} onClick={() => setDialog("assign")}>
            Assign renewal
          </Button>
          <Button variant="ghost" icon={Check} onClick={() => setDialog("completed")}>
            Mark completed
          </Button>
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Renewal history" meta={`${r.renewals.length}`}>
            {r.renewals.length === 0 ? (
              <EmptyState icon={RefreshCcw} title="No renewals recorded" compact />
            ) : (
              <ul className="divide-y divide-line">
                {r.renewals.map((x) => (
                  <li key={x.id} className="px-4 py-3 text-[13.5px] sm:px-5">
                    Renewed {fmtDate(x.registration_date)}, now expires <span className="font-medium">{fmtDate(x.new_expiry)}</span>
                    <span className="block text-[12.5px] text-ink-3">
                      {x.registration_number ? `${x.registration_number} · ` : ""}
                      {x.cost_php ? `${peso(x.cost_php)} · ` : ""}
                      {x.filed_by.name} · {fmtDate(x.at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {r.tasks.length > 0 && (
            <Panel title="Renewal tasks">
              <ul className="divide-y divide-line">
                {r.tasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-[13.5px] sm:px-5">
                    <ListTodo className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      {t.title}
                      <span className="block text-[12.5px] text-ink-3">
                        {t.assignee?.name ?? "Unassigned"} · due {fmtDate(t.due_date)} · {t.status.replace("_", " ")}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
        <aside className="flex flex-col gap-5">
          <Panel title="Information" actions={open ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Valid for", r.validity_years ? `${r.validity_years} year${r.validity_years > 1 ? "s" : ""}` : "—"],
                ["Site", r.site ?? "—"],
                ["Company", r.company.name],
              ]
                .filter(([, v]) => v !== "—")
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
            {r.notes && <p className="whitespace-pre-line border-t border-line px-4 py-3 text-[13.5px] text-ink-2 sm:px-5">{r.notes}</p>}
          </Panel>
          <DocumentsPanel relatedType="registration" relatedId={r.id} />
          <RecordAttachments ownerType="registration" ownerId={r.id} items={r.attachments} canAdd={open} onChange={q.reload} />
          {open && me?.role === "admin" && (
            <div className="flex gap-2">
              <Button variant="danger" size="sm" icon={Ban} onClick={() => setDialog("terminated")}>
                Terminate
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setDialog("void")}>
                Void
              </Button>
            </div>
          )}
        </aside>
      </div>

      <RecordDialog
        open={Boolean(spec)}
        onClose={() => setDialog(null)}
        title={spec?.title ?? ""}
        fields={spec ? [...spec.fields] : []}
        initial={spec && "initial" in spec ? spec.initial : undefined}
        scan={dialog === "renew" ? { kind: "registration", attachTo: "registration", ownerId: r.id } : undefined}
        onSubmit={async (p) => {
          await api(spec!.url, { method: "method" in spec! ? spec.method : "POST", json: { ...p, ...("extra" in spec! ? spec.extra : {}) } });
          toast(spec!.done);
          q.reload();
          invalidate();
        }}
      />
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- BOC */

const BOC_FIELDS: FieldDef[] = [
  { name: "direction", label: "Direction", type: "select", required: true, half: true, options: [{ value: "import", label: "Import" }, { value: "export", label: "Export" }] },
  { name: "eta", label: "ETA / ship date", type: "date", half: true },
  { name: "description", label: "Goods", required: true, placeholder: "e.g. Lab reagents, 12 cartons" },
  { name: "bill_of_lading", label: "Bill of lading / AWB", half: true },
  { name: "officer_id", label: "Assigned officer", type: "person", half: true },
  { name: "shipment_reference", label: "Shipment reference", more: true, half: true },
  { name: "entry_number", label: "Import/export entry no.", more: true, half: true },
  { name: "counterparty", label: "Supplier / consignee", more: true, half: true },
  { name: "broker", label: "Customs broker", more: true, half: true },
  { name: "origin", label: "Origin", more: true, half: true },
  { name: "destination", label: "Destination", more: true, half: true },
];

export function BocPage() {
  const toast = useToast();
  const [state, setState] = useState<"open" | "closed">("open");
  const data = useApi<Boc[]>(`/api/v1/compliance/boc?state=${state}`);
  const [creating, setCreating] = useState(false);
  return (
    <ModuleShell
      group="compliance"
      item="boc"
      summary="Importations and exportations through the Bureau of Customs, from lodgement to release."
      actions={
        <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
          New BOC case
        </Button>
      }
    >
      <Panel>
        <div className="flex gap-1.5 border-b border-line p-3 sm:px-5">
          <Chip on={state === "open"} onClick={() => setState("open")}>
            Open
          </Chip>
          <Chip on={state === "closed"} onClick={() => setState("closed")}>
            Closed
          </Chip>
        </div>
        {!data.data ? (
          <SkeletonRows />
        ) : data.data.length === 0 ? (
          <EmptyState icon={Ship} title={state === "open" ? "No open BOC cases" : "No closed cases yet"} compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.map((c) => (
              <li key={c.id}>
                <Link href={`/boc/${c.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
                  <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line sm:mt-0" aria-hidden="true">
                    <Ship className="size-5" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-bold">{c.description}</span>
                    <span className="block text-[12.5px] text-ink-3">
                      <span className="tabular">{c.reference}</span> · {c.direction === "import" ? "Import" : "Export"}
                      {c.bill_of_lading ? ` · BL ${c.bill_of_lading}` : ""}
                      {c.officer ? ` · ${c.officer.name}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-right text-[12.5px]">
                    <span className="block font-medium">{MILESTONE_LABEL[c.status]}</span>
                    {c.eta && <span className="text-ink-3">ETA {fmtDate(c.eta)}</span>}
                  </span>
                  <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New BOC case"
        fields={BOC_FIELDS}
        initial={{ direction: "import" }}
        submitLabel="Open case"
        onSubmit={async (p) => {
          const c = await post<Boc>("/api/v1/compliance/boc", p);
          toast(`Opened · ${c.reference}`);
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

export function BocDetailView({ id }: { id: number }) {
  const toast = useToast();
  const q = useApi<BocDetail>(`/api/v1/compliance/boc/${id}`);
  const [dialog, setDialog] = useState<null | "edit" | "note" | "advance" | "cancel">(null);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This case doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const c = q.data;
  if (!c) return <PageFrame><SkeletonRows /></PageFrame>;
  const closed = c.status === "closed" || c.status === "cancelled";
  const reached = MILESTONES.indexOf(c.status);
  const next = c.next[0];
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Corporate Compliance", href: "/compliance/boc" }, { label: c.reference }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Ship className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {c.reference} · BOC {c.direction}
            {c.eta ? ` · ETA ${fmtDate(c.eta)}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">{c.description}</h1>
          <p className="mt-2 text-[14px] text-ink-2">{c.officer ? `Officer: ${c.officer.name}` : "No officer assigned"}</p>
        </div>
      </header>

      <section className="mt-6 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 sm:p-5">
        <ol className="flex flex-col gap-2 sm:flex-row sm:gap-0" aria-label="Milestones">
          {MILESTONES.map((m, i) => {
            const done = c.status !== "cancelled" && i <= reached;
            const current = i === reached && !closed;
            return (
              <li key={m} className="flex items-center gap-2 sm:flex-1 sm:flex-col sm:items-start">
                <span className="flex items-center sm:w-full">
                  <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full", done ? "bg-ink text-white" : "bg-sheet ring-1 ring-edge", current && "ring-2 ring-accent")} aria-hidden="true">
                    {done ? <Check className="size-3.5" strokeWidth={2.5} /> : <span className="size-1.5 rounded-full bg-mute" />}
                  </span>
                  {i < MILESTONES.length - 1 && <span className={cn("ml-1 hidden h-px flex-1 sm:block", i < reached ? "bg-ink" : "bg-edge")} aria-hidden="true" />}
                </span>
                <span className={cn("text-[13px]", current ? "font-bold" : done ? "text-ink-2" : "text-ink-3")}>{MILESTONE_LABEL[m]}</span>
              </li>
            );
          })}
        </ol>
        {c.status === "cancelled" && <p className="mt-3 text-[14px] font-medium text-danger">Cancelled</p>}
        {!closed && (
          <div className="mt-4 flex flex-wrap gap-2">
            {next && (
              <Button variant="primary" icon={Check} onClick={() => setDialog("advance")}>
                Mark {MILESTONE_LABEL[next].toLowerCase()}
              </Button>
            )}
            <Button icon={MessageSquare} onClick={() => setDialog("note")}>
              Add note
            </Button>
            <Button variant="ghost" icon={Ban} onClick={() => setDialog("cancel")}>
              Cancel case
            </Button>
          </div>
        )}
      </section>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <Panel title="Submission history">
          <ol className="px-4 py-4 sm:px-5">
            {c.events.map((e, i) => (
              <li key={e.id} className="relative flex gap-3 pb-4 last:pb-0">
                {i < c.events.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-line" aria-hidden="true" />}
                <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full bg-sheet ring-1 ring-edge" aria-hidden="true">
                  {e.milestone ? <Check className="size-3.5" strokeWidth={2} /> : <MessageSquare className="size-3.5" strokeWidth={2} />}
                </span>
                <div className="min-w-0 pt-0.5 text-[13.5px]">
                  <p>
                    <span className="font-medium">{e.milestone ? MILESTONE_LABEL[e.milestone] : "Note"}</span>
                    <span className="text-ink-3"> · {e.actor.name} · {fmtRelative(e.at)}</span>
                  </p>
                  {e.note && <p className="mt-0.5 text-ink-2">{e.note}</p>}
                </div>
              </li>
            ))}
          </ol>
        </Panel>
        <aside className="flex flex-col gap-5">
          <Panel title="Shipment" actions={!closed ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Bill of lading", c.bill_of_lading],
                ["Entry no.", c.entry_number],
                ["Shipment ref.", c.shipment_reference],
                [c.direction === "import" ? "Supplier" : "Consignee", c.counterparty],
                ["Broker", c.broker],
                ["Route", [c.origin, c.destination].filter(Boolean).join(" → ") || null],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k as string} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
          </Panel>
          <DocumentsPanel relatedType="boc" relatedId={c.id} />
          <RecordAttachments ownerType="boc" ownerId={c.id} items={c.attachments} canAdd={!closed} onChange={q.reload} />
        </aside>
      </div>

      <RecordDialog
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        title="Edit shipment"
        fields={BOC_FIELDS}
        initial={fromRecord(BOC_FIELDS, { ...c, officer_id: c.officer?.id } as unknown as Record<string, unknown>)}
        onSubmit={async (p) => {
          await api(`/api/v1/compliance/boc/${c.id}`, { method: "PATCH", json: p });
          toast("Saved");
          q.reload();
        }}
      />
      <RecordDialog
        open={dialog === "note" || dialog === "advance" || dialog === "cancel"}
        onClose={() => setDialog(null)}
        title={dialog === "advance" && next ? `Mark ${MILESTONE_LABEL[next].toLowerCase()}` : dialog === "cancel" ? "Cancel this case" : "Add a note"}
        fields={[{ name: "note", label: dialog === "cancel" ? "Reason" : dialog === "advance" ? "Note (optional)" : "Note", type: "textarea", required: dialog !== "advance" }]}
        onSubmit={async (p) => {
          const res = await post<BocDetail>(`/api/v1/compliance/boc/${c.id}/events`, { ...p, milestone: dialog === "advance" ? next : dialog === "cancel" ? "cancelled" : null });
          q.setData(res);
          toast("Updated");
          invalidate();
        }}
      />
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- renewal calendar */

type CalItem = { date: string; days: number; kind: string; module: "compliance" | "boc" | "fleet" | "contract"; title: string; subtitle: string; company: string; href: string };
const MODULE_ICON: Record<CalItem["module"], LucideIcon> = { compliance: Landmark, boc: Ship, fleet: CarFront, contract: FileText };
const MONTH = new Intl.DateTimeFormat("en-PH", { month: "long", year: "numeric" });

/** Every due date across modules, soonest first (Home › Upcoming renewals). */
export function RenewalCalendar() {
  const [months, setMonths] = useState(6);
  const data = useApi<CalItem[]>(`/api/v1/compliance/calendar?months=${months}`);
  const overdue = data.data?.filter((i) => i.days < 0) ?? [];
  const upcoming = data.data?.filter((i) => i.days >= 0) ?? [];
  const byMonth = new Map<string, CalItem[]>();
  for (const i of upcoming) {
    const key = i.date.slice(0, 7);
    byMonth.set(key, [...(byMonth.get(key) ?? []), i]);
  }
  const row = (i: CalItem) => {
    const I = MODULE_ICON[i.module];
    const dt = new Date(`${i.date}T00:00:00`);
    return (
      <li key={`${i.href}-${i.kind}`}>
        <Link href={i.href} className="flex items-center gap-3.5 px-4 py-3 hover:bg-canvas sm:px-5">
          <span className={cn("flex w-11 shrink-0 flex-col items-center rounded-[8px] border py-1", i.days < 0 ? "border-danger/40 text-danger" : i.days <= 7 ? "border-ink" : "border-line")} aria-hidden="true">
            <span className="text-[10.5px] font-medium uppercase leading-none tracking-wide">{dt.toLocaleString("en-PH", { month: "short" })}</span>
            <span className="tabular text-[17px] font-bold leading-tight">{dt.getDate()}</span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-[14.5px] font-bold">
              <I className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
              <span className="truncate">{i.title}</span>
            </span>
            <span className="block text-[12.5px] text-ink-3">
              {i.subtitle} · {i.kind} · {i.company}
            </span>
          </span>
          <span className="shrink-0 text-[12.5px]">
            <DueLabel days={i.days} />
          </span>
        </Link>
      </li>
    );
  };
  return (
    <ModuleShell group="dashboard" item="upcoming-renewals" summary="Every permit, registration, customs ETA, vehicle renewal and lease end on one timeline, soonest first.">
      <div className="mb-4 flex gap-1.5">
        {[3, 6, 12].map((n) => (
          <Chip key={n} on={months === n} onClick={() => setMonths(n)}>
            Next {n} months
          </Chip>
        ))}
      </div>
      {!data.data ? (
        <Panel>
          <SkeletonRows />
        </Panel>
      ) : data.data.length === 0 ? (
        <Panel>
          <EmptyState icon={CalendarClock} title="No upcoming due dates" body="Add registrations, BOC cases or vehicles to fill the calendar." compact />
        </Panel>
      ) : (
        <div className="flex flex-col gap-5">
          {overdue.length > 0 && (
            <Panel title="Overdue" meta={`${overdue.length}`}>
              <ul className="divide-y divide-line">{overdue.map(row)}</ul>
            </Panel>
          )}
          {[...byMonth.entries()].map(([m, items]) => (
            <Panel key={m} title={MONTH.format(new Date(`${m}-01T00:00:00`))} meta={`${items.length}`}>
              <ul className="divide-y divide-line">{items.map(row)}</ul>
            </Panel>
          ))}
        </div>
      )}
    </ModuleShell>
  );
}

