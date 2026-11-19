"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Ban, Building, CalendarClock, Check, ChevronRight, FileSignature, House, Landmark, Pencil, Plus, RefreshCcw, Send, TriangleAlert, Users, Wallet, X } from "lucide-react";
import { api, fmtDate, fmtRelative, invalidate, post, qs, useApi, type Attachment, type Person } from "@/lib/api";
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

type Lessor = { id: number; name: string; contact_person: string | null; phone: string | null; email: string | null; address: string | null; notes: string | null; active_contracts?: number; monthly_rent_php?: string; sites?: string[] };
type Contract = {
  id: number;
  reference: string;
  company: { id: number; code: string; name: string };
  contract_type: "office_lease" | "staff_house" | "other";
  type_label: string;
  title: string;
  property_name: string | null;
  location: string | null;
  lessor: { id: number; name: string } | null;
  start_date: string;
  end_date: string;
  covered_year: string;
  monthly_rent_php: string | null;
  deposit_php: string | null;
  rent_due_day: number | null;
  renewal_notice_days: number;
  renewal_due: string;
  days_left: number;
  occupants: string | null;
  status: "active" | "for_renewal" | "expired" | "renewed" | "terminated";
  external_reference: string | null;
  responsible: Person | null;
  notes: string | null;
  version: number;
};
type Rent = { id: number; reference: string; contract: { id: number; reference: string; title: string; lessor: string | null }; period: string; amount_php: string; due_date: string; days_left: number; status: "due" | "sent" | "paid" | "cancelled"; finance_reference: string | null };
type ContractDetail = Contract & { events: { id: number; type: string; message: string | null; actor: Person | null; at: string }[]; rent_payments: Rent[]; attachments: Attachment[]; history: { id: number; reference: string; start_date: string; end_date: string; monthly_rent_php: string | null }[]; renewed_to: { id: number; reference: string } | null };

const STATUS: Record<Contract["status"], string> = { active: "Active", for_renewal: "For renewal", expired: "Expired", renewed: "Renewed", terminated: "Terminated" };
const TYPE_ICON = { office_lease: Building, staff_house: House, other: FileSignature };

function Pill({ s }: { s: Contract["status"] }) {
  return (
    <span className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[12.5px] font-medium whitespace-nowrap", s === "expired" ? "border-danger/30 bg-danger-soft text-danger" : s === "for_renewal" ? "border-ink" : s === "active" ? "border-edge" : "border-line bg-canvas text-ink-3")}>
      {s === "for_renewal" && <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" />}
      {STATUS[s]}
    </span>
  );
}

function contractFields(type?: Contract["contract_type"]): FieldDef[] {
  return [
    { name: "title", label: "Contract", required: true, placeholder: type === "staff_house" ? "e.g. Staff house, Pasig" : "e.g. HQ office lease, 12F" },
    { name: "contract_type", label: "Type", type: "select", required: true, half: true, options: [{ value: "office_lease", label: "Office lease" }, { value: "staff_house", label: "Staff house" }, { value: "other", label: "Other contract" }] },
    { name: "lessor_id", label: "Lessor", type: "select", half: true, options: [] },
    { name: "start_date", label: "Start", type: "date", required: true, half: true },
    { name: "end_date", label: "End", type: "date", required: true, half: true },
    { name: "monthly_rent_php", label: "Monthly rent", type: "money", half: true },
    { name: "rent_due_day", label: "Rent due day", type: "number", half: true, hint: "Day of the month" },
    { name: "property_name", label: "Property / site", more: true, half: true },
    { name: "location", label: "Address", more: true, half: true },
    { name: "deposit_php", label: "Deposit", type: "money", more: true, half: true },
    { name: "renewal_notice_days", label: "Remind before end (days)", type: "number", more: true, half: true },
    { name: "responsible_id", label: "Responsible", type: "person", more: true, half: true },
    { name: "external_reference", label: "Bishnoi One Contracts reference", more: true, half: true, hint: "If the signed contract is managed there" },
    { name: "occupants", label: "Occupants (staff houses)", type: "textarea", more: true },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
}

function useContractFields(type?: Contract["contract_type"]) {
  const lessors = useApi<Lessor[]>("/api/v1/contracts/lessors");
  return contractFields(type).map((f) => (f.name === "lessor_id" ? { ...f, options: (lessors.data ?? []).map((l) => ({ value: String(l.id), label: l.name })) } : f));
}

function ContractRow({ c }: { c: Contract }) {
  const I = TYPE_ICON[c.contract_type];
  return (
    <li>
      <Link href={`/contract/${c.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line sm:mt-0" aria-hidden="true">
          <I className="size-5" strokeWidth={1.6} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold">{c.title}</span>
          <span className="block text-[12.5px] text-ink-3">
            {c.lessor?.name ?? "No lessor"} · {fmtDate(c.start_date)} – {fmtDate(c.end_date)}
            {c.monthly_rent_php ? ` · ${peso(c.monthly_rent_php)}/mo` : ""}
          </span>
          <span className="mt-1 block text-[12.5px] sm:hidden">{["active", "for_renewal", "expired"].includes(c.status) && <DueLabel days={c.days_left} label="Ends" />}</span>
        </span>
        <span className="hidden shrink-0 flex-col items-end gap-1 text-[12.5px] sm:flex">
          <Pill s={c.status} />
          {["active", "for_renewal", "expired"].includes(c.status) && <DueLabel days={c.days_left} label="Ends" />}
        </span>
        <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}

type ContractView = "all" | "office_lease" | "staff_house" | "ending";
const CONTRACT_VIEWS: { value: ContractView; label: string }[] = [
  { value: "all", label: "All" },
  { value: "office_lease", label: "Office leases" },
  { value: "staff_house", label: "Staff house" },
  { value: "ending", label: "Ending in 120 days" },
];

/** The one contract register; office leases, staff houses and the ones ending soon are filters. */
export function ContractsList({ view = "all" }: { view?: ContractView }) {
  const toast = useToast();
  const [tab, setTab] = useState<ContractView>(view);
  const type = tab === "office_lease" || tab === "staff_house" ? tab : undefined;
  const [history, setHistory] = useState(false);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const data = useApi<{ items: Contract[]; summary: { active: number; for_renewal: number; expired: number; monthly_rent_php: string } }>(`/api/v1/contracts${qs({ contract_type: type, include_history: history, due_within: tab === "ending" ? 120 : undefined, q })}`);
  const fields = useContractFields(type);
  const s = data.data?.summary;
  return (
    <ModuleShell
      group="contracts"
      item="registry"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Add contract
          </Button>
          <DataTools dataset="contracts" statuses={Object.entries(STATUS).map(([value, label]) => ({ value, label }))} />
        </>
      }
    >
      {tab === "all" && (
        <div className="mb-5">
          <CountStrip
            items={[
              { icon: Check, label: "Active", value: s?.active, href: "/contracts/registry" },
              { icon: RefreshCcw, label: "For renewal", value: s?.for_renewal, href: "/contracts/renewals" },
              { icon: TriangleAlert, label: "Expired", value: s?.expired, href: "/contracts/renewals", danger: true },
              { icon: Wallet, label: "Monthly rent", value: s ? peso(s.monthly_rent_php) : undefined, href: "/contracts/rent" },
            ]}
          />
        </div>
      )}
      <Panel>
        <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
          <Input type="search" placeholder="Search contract, site or lessor" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0">
            {CONTRACT_VIEWS.map((v) => (
              <Chip key={v.value} on={tab === v.value} onClick={() => setTab(v.value)}>
                {v.label}
              </Chip>
            ))}
            <span className="mx-1 w-px shrink-0 self-stretch bg-line" aria-hidden="true" />
            <Chip on={history} onClick={() => setHistory((h) => !h)}>
              Include renewed
            </Chip>
          </div>
        </div>
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState icon={tab === "ending" ? CalendarClock : FileSignature} title={tab === "ending" ? "No contracts ending within 120 days" : "No contracts here yet"} body="Add leases to track rent and get reminders before they end." compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((c) => (
              <ContractRow key={c.id} c={c} />
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a contract"
        fields={fields}
        initial={{ contract_type: type ?? "office_lease", renewal_notice_days: "60" }}
        submitLabel="Add"
        attach={{ ownerType: "contract", title: "Attach the signed contract" }}
        onSubmit={async (p) => {
          const c = await post<Contract>("/api/v1/contracts", { ...p, renewal_notice_days: p.renewal_notice_days ?? 60 });
          toast(`Added · ${c.reference}`);
          invalidate();
          return c;
        }}
      />
    </ModuleShell>
  );
}

/** This month's rent per active lease, handed off to Finance. */
export function RentPage() {
  const toast = useToast();
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const rent = useApi<Rent[]>(`/api/v1/contracts/rent/payments?period=${period}`);
  const [acting, setActing] = useState<{ r: Rent; action: "paid" | "cancel" } | null>(null);
  async function prepare() {
    try {
      const r = await post<{ created: number }>("/api/v1/contracts/rent/prepare", { period });
      toast(r.created ? `${r.created} rent line(s) prepared` : "This month is already prepared");
      invalidate();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  async function send(r: Rent) {
    await post(`/api/v1/contracts/rent/payments/${r.id}/send`, {});
    toast(`Sent to Finance · ${r.reference}`);
    invalidate();
  }
  return (
    <ModuleShell group="contracts" item="rent">
      <div className="flex flex-col gap-5">
        <Panel
          title="Monthly rent"
          actions={
            <span className="flex items-center gap-2">
              <Input aria-label="Month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="h-9 w-[150px] md:h-9" />
              <Button size="sm" icon={Plus} onClick={prepare}>
                Generate rent schedule
              </Button>
            </span>
          }
        >
          {!rent.data ? (
            <SkeletonRows rows={2} />
          ) : rent.data.length === 0 ? (
            <EmptyState icon={Wallet} title="No rent lines for this month" body="Prepare the month to list every active lease with a monthly rent." compact />
          ) : (
            <ul className="divide-y divide-line">
              {rent.data.map((r) => (
                <li key={r.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:px-5">
                  <span className="min-w-0 flex-1">
                    <Link href={`/contract/${r.contract.id}`} className="block truncate text-[14px] font-medium hover:underline">
                      {r.contract.title}
                    </Link>
                    <span className="block text-[12.5px] text-ink-3">
                      <span className="tabular">{peso(r.amount_php)}</span> · due {fmtDate(r.due_date)} · {r.status === "due" ? "Not sent" : r.status === "sent" ? "With Finance" : r.status === "paid" ? `Paid · ${r.finance_reference}` : "Cancelled"}
                    </span>
                  </span>
                  <span className="flex gap-2">
                    {r.status === "due" && (
                      <Button size="sm" variant="primary" icon={Send} onClick={() => send(r)}>
                        Send to Finance
                      </Button>
                    )}
                    {r.status === "sent" && (
                      <Button size="sm" variant="primary" icon={Check} onClick={() => setActing({ r, action: "paid" })}>
                        Record payment
                      </Button>
                    )}
                    {(r.status === "due" || r.status === "sent") && <Button size="sm" variant="ghost" icon={X} aria-label="Cancel" onClick={() => setActing({ r, action: "cancel" })} />}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <RecordDialog
        open={Boolean(acting)}
        onClose={() => setActing(null)}
        title={acting?.action === "paid" ? "Record rent payment" : "Cancel rent line"}
        description={acting ? `${acting.r.contract.title} · ${acting.r.period}` : undefined}
        fields={acting?.action === "paid" ? [{ name: "finance_reference", label: "Finance payment reference", required: true }] : [{ name: "reason", label: "Reason", type: "textarea", required: true }]}
        onSubmit={async (p) => {
          await post(`/api/v1/contracts/rent/payments/${acting!.r.id}/${acting!.action}`, p);
          toast("Updated");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

export function LessorsPage() {
  const toast = useToast();
  const data = useApi<Lessor[]>("/api/v1/contracts/lessors");
  const [editing, setEditing] = useState<Lessor | "new" | null>(null);
  const fields: FieldDef[] = [
    { name: "name", label: "Lessor", required: true },
    { name: "contact_person", label: "Contact person", half: true },
    { name: "phone", label: "Phone", half: true },
    { name: "email", label: "Email", half: true },
    { name: "address", label: "Address", half: true },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
  return (
    <ModuleShell
      group="contracts"
      item="lessors"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>
            Add lessor
          </Button>
          <DataTools dataset="lessors" />
        </>
      }
    >
      <Panel>
        {!data.data ? (
          <SkeletonRows />
        ) : data.data.length === 0 ? (
          <EmptyState icon={Users} title="No lessors yet" compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.map((l) => (
              <li key={l.id} className="flex items-start gap-3.5 px-4 py-3.5 sm:px-5">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line" aria-hidden="true">
                  <Landmark className="size-5" strokeWidth={1.6} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-bold">{l.name}</span>
                  <span className="block text-[12.5px] text-ink-3">{[l.contact_person, l.phone, l.email].filter(Boolean).join(" · ") || "No contact details"}</span>
                  <span className="block text-[12.5px] text-ink-2">
                    {l.active_contracts ? `${l.active_contracts} active · ${peso(l.monthly_rent_php)}/mo · ${l.sites?.join(", ")}` : "No active contracts"}
                  </span>
                </span>
                <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${l.name}`} onClick={() => setEditing(l)} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add a lessor" : "Edit lessor"}
        fields={fields}
        initial={editing && editing !== "new" ? fromRecord(fields, editing as unknown as Record<string, unknown>) : undefined}
        onSubmit={async (p) => {
          if (editing === "new") await post("/api/v1/contracts/lessors", p);
          else await api(`/api/v1/contracts/lessors/${(editing as Lessor).id}`, { method: "PATCH", json: p });
          toast("Saved");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

export function ContractDetailView({ id }: { id: number }) {
  const toast = useToast();
  const router = useRouter();
  const { me } = useShell();
  const q = useApi<ContractDetail>(`/api/v1/contracts/${id}`);
  const [dialog, setDialog] = useState<null | "edit" | "renew" | "terminate">(null);
  const fields = useContractFields(q.data?.contract_type);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This contract doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const c = q.data;
  if (!c) return <PageFrame><SkeletonRows /></PageFrame>;
  const live = ["active", "for_renewal", "expired"].includes(c.status);
  const I = TYPE_ICON[c.contract_type];
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Contracts", href: "/contracts/registry" }, { label: c.reference }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <I className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {c.reference} · {c.type_label} · {c.covered_year}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">{c.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[13.5px] text-ink-2">
            <Pill s={c.status} />
            {c.lessor?.name}
            {live && <DueLabel days={c.days_left} label="Ends" />}
          </div>
        </div>
      </header>
      {live && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="primary" icon={RefreshCcw} onClick={() => setDialog("renew")}>
            Record renewal
          </Button>
          {me?.role === "admin" && (
            <Button variant="ghost" icon={Ban} onClick={() => setDialog("terminate")}>
              Terminate
            </Button>
          )}
        </div>
      )}
      {c.renewed_to && (
        <p className="mt-5 text-[14px]">
          Renewed as{" "}
          <Link href={`/contract/${c.renewed_to.id}`} className="font-medium underline">
            {c.renewed_to.reference}
          </Link>
          .
        </p>
      )}
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Rent" meta={c.monthly_rent_php ? `${peso(c.monthly_rent_php)}/mo` : undefined}>
            {c.rent_payments.length === 0 ? (
              <p className="px-4 py-3 text-[13px] text-ink-3 sm:px-5">No rent lines yet. Prepare a month in Renewals.</p>
            ) : (
              <ul className="divide-y divide-line">
                {c.rent_payments.map((r) => (
                  <li key={r.id} className="flex justify-between gap-3 px-4 py-2.5 text-[13.5px] sm:px-5">
                    <span>{r.period}</span>
                    <span className="tabular text-ink-2">
                      {peso(r.amount_php)} · {r.status === "paid" ? `Paid ${r.finance_reference}` : r.status === "sent" ? "With Finance" : r.status === "due" ? `Due ${fmtDate(r.due_date)}` : "Cancelled"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="History">
            <ol className="px-4 py-4 sm:px-5">
              {c.events.map((e) => (
                <li key={e.id} className="pb-3 text-[13.5px] last:pb-0">
                  <span className="font-medium">{e.type.replace(/_/g, " ").replace(/^\w/, (x) => x.toUpperCase())}</span>
                  <span className="text-ink-3"> · {e.actor?.name ?? "System"} · {fmtRelative(e.at)}</span>
                  {e.message && <span className="block text-ink-2">{e.message}</span>}
                </li>
              ))}
              {c.history.map((h) => (
                <li key={h.id} className="pb-3 text-[13.5px] last:pb-0">
                  Previous term{" "}
                  <Link href={`/contract/${h.id}`} className="font-medium underline">
                    {h.reference}
                  </Link>
                  <span className="text-ink-3">
                    {" "}
                    · {fmtDate(h.start_date)} – {fmtDate(h.end_date)}
                    {h.monthly_rent_php ? ` · ${peso(h.monthly_rent_php)}/mo` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
        <aside className="flex flex-col gap-5">
          <Panel title="Information" actions={live ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Term", `${fmtDate(c.start_date)} – ${fmtDate(c.end_date)}`],
                ["Remind from", fmtDate(c.renewal_due)],
                ["Site", c.property_name ?? ""],
                ["Address", c.location ?? ""],
                ["Deposit", c.deposit_php ? peso(c.deposit_php) : ""],
                ["Rent due", c.rent_due_day ? `Day ${c.rent_due_day}` : ""],
                ["Responsible", c.responsible?.name ?? ""],
                ["Contracts ref.", c.external_reference ?? ""],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
            {c.occupants && <p className="border-t border-line px-4 py-3 text-[13px] text-ink-2 sm:px-5">Occupants: {c.occupants}</p>}
          </Panel>
          <DocumentsPanel relatedType="contract" relatedId={c.id} />
          <RecordAttachments ownerType="contract" ownerId={c.id} items={c.attachments} canAdd={live} onChange={q.reload} />
        </aside>
      </div>
      <RecordDialog
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        title="Edit contract"
        fields={fields}
        initial={fromRecord(fields, { ...c, lessor_id: c.lessor?.id, responsible_id: c.responsible?.id } as unknown as Record<string, unknown>)}
        onSubmit={async (p) => {
          await api(`/api/v1/contracts/${c.id}`, { method: "PATCH", json: { ...p, renewal_notice_days: p.renewal_notice_days ?? 60, version: c.version } });
          toast("Saved");
          q.reload();
        }}
      />
      <RecordDialog
        open={dialog === "renew"}
        onClose={() => setDialog(null)}
        title="Record the renewal"
        description="Creates the new term as its own record and keeps this one as history."
        fields={[
          { name: "start_date", label: "New start", type: "date", required: true, half: true },
          { name: "end_date", label: "New end", type: "date", required: true, half: true },
          { name: "monthly_rent_php", label: "New monthly rent", type: "money", half: true, hint: "Leave empty to keep the current rent" },
          { name: "external_reference", label: "Bishnoi One Contracts reference", half: true },
          { name: "notes", label: "Notes", type: "textarea", more: true },
        ]}
        submitLabel="Save renewal"
        attach={{ ownerType: "contract", title: "Attach the signed contract" }}
        onSubmit={async (p) => {
          const n = await post<Contract>(`/api/v1/contracts/${c.id}/renew`, p);
          toast(`Renewed · ${n.reference}`);
          router.push(`/contract/${n.id}`);
          return n;
        }}
      />
      <RecordDialog
        open={dialog === "terminate"}
        onClose={() => setDialog(null)}
        title="Terminate contract"
        fields={[
          { name: "reason", label: "Reason", type: "textarea", required: true },
          { name: "effective_date", label: "Effective date", type: "date", half: true },
        ]}
        submitLabel="Terminate"
        onSubmit={async (p) => {
          await post(`/api/v1/contracts/${c.id}/terminate`, p);
          toast("Terminated");
          q.reload();
        }}
      />
    </PageFrame>
  );
}
