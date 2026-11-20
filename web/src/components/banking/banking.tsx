"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Ban, Check, ChevronRight, CreditCard, Files, HandCoins, Landmark, Lock, Pencil, Plus, RefreshCcw, Send, X } from "lucide-react";
import { api, fmtDate, invalidate, post, qs, useApi, type ApiError, type Attachment, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { ActionRow, Button, Chip } from "@/components/ui/controls";
import { EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { RecordAttachments } from "@/components/assets/assets";
import { DueLabel, peso } from "@/components/fleet/fleet";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { cn } from "@/lib/cn";

type Card = { id: number; reference: string; bank: string; card_type: string; card_masked: string; custodian: Person; expiry: string; expiry_date: string; days_to_expiry: number; credit_limit_php: string | null; status: string; notes: string | null };
type Case = {
  company?: { id: number; code: string };
  updated_at?: string;
  id: number;
  reference: string;
  bank: string;
  case_type: string;
  type_label: string;
  subject: string;
  account_masked: string | null;
  card: Card | null;
  responsible: Person | null;
  application_date: string | null;
  renewal_date: string | null;
  days_to_renewal: number | null;
  requirements: { name: string; done: boolean }[];
  requirements_done: number;
  status: "open" | "submitted" | "approved" | "completed" | "rejected" | "cancelled";
  finance_status: "not_needed" | "pending" | "sent" | "confirmed" | "rejected";
  finance_reference: string | null;
  notes: string | null;
};
type CaseDetail = Case & { attachments: Attachment[] };

const SAFETY = "Only the last 4 digits are kept. Never enter full card or account numbers, CVV, PINs or online-banking passwords.";
const CASE_STATUS: Record<Case["status"], string> = { open: "Open", submitted: "Submitted to bank", approved: "Approved by bank", completed: "Completed", rejected: "Rejected", cancelled: "Cancelled" };
const FIN_STATUS: Record<Case["finance_status"], string> = { not_needed: "No Finance action", pending: "Finance: to send", sent: "With Finance", confirmed: "Finance confirmed", rejected: "Finance rejected" };

function Locked() {
  return <EmptyState icon={Lock} title="Restricted records" body="Banking records need explicit access. An Admin can grant it in Settings › People & access." compact />;
}

function caseFields(type?: string): FieldDef[] {
  return [
    { name: "subject", label: "Subject", required: true, placeholder: type === "account_application" ? "e.g. Payroll account for 2MG" : "e.g. Card for the Operations Head" },
    { name: "bank", label: "Bank", required: true, half: true },
    { name: "responsible_id", label: "Responsible", type: "person", half: true },
    { name: "application_date", label: "Application date", type: "date", half: true },
    { name: "renewal_date", label: "Renewal / due date", type: "date", half: true },
    { name: "finance_status", label: "Needs Finance?", type: "select", half: true, options: [{ value: "not_needed", label: "No" }, { value: "pending", label: "Yes" }] },
    { name: "account_last4", label: "Account / card (last 4 digits)", half: true, more: true, hint: "Optional. Never the full number." },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
}

function CaseRow({ c }: { c: Case }) {
  return (
    <li>
      <Link href={`/bank-case/${c.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line sm:mt-0" aria-hidden="true">
          <Landmark className="size-5" strokeWidth={1.6} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold">{c.subject}</span>
          <span className="block text-[12.5px] text-ink-3">
            {c.bank} · {c.type_label}
            {c.requirements.length ? ` · ${c.requirements_done}/${c.requirements.length} requirements` : ""}
            {c.finance_status !== "not_needed" ? ` · ${FIN_STATUS[c.finance_status]}` : ""}
          </span>
        </span>
        <span className="shrink-0 text-right text-[12.5px]">
          <span className="block font-medium">{CASE_STATUS[c.status]}</span>
          {c.renewal_date && c.status !== "completed" && <DueLabel days={c.days_to_renewal} />}
        </span>
        <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}

type CaseView = "all" | "account" | "documentation" | "finance";
const CASE_VIEWS: { value: CaseView; label: string; types: string[]; finance?: boolean; newType: string; button: string }[] = [
  { value: "all", label: "All", types: [], newType: "account_application", button: "New bank request" },
  { value: "account", label: "Account applications", types: ["account_application"], newType: "account_application", button: "New application" },
  { value: "documentation", label: "Documentation", types: ["documentation", "bank_renewal"], newType: "documentation", button: "New documentation case" },
  { value: "finance", label: "Finance coordination", types: ["finance_coordination", "card_request", "card_renewal"], finance: true, newType: "finance_coordination", button: "New Finance case" },
];
const NEW_CASE_TYPES = [
  { value: "account_application", label: "Bank account application" },
  { value: "documentation", label: "Bank documentation" },
  { value: "bank_renewal", label: "Bank renewal / KYC update" },
  { value: "finance_coordination", label: "Finance coordination" },
];

/** Account applications, bank documentation and Finance coordination in one list, filtered by kind. */
export function CasesPage({ view = "all" }: { view?: CaseView }) {
  const toast = useToast();
  const [tab, setTab] = useState<CaseView>(view);
  const v = CASE_VIEWS.find((x) => x.value === tab)!;
  const [state, setState] = useState<"open" | "closed">("open");
  const data = useApi<Case[]>(`/api/v1/banking/cases${qs({ case_type: v.types.length ? v.types : undefined, state, finance: v.finance })}`);
  const [creating, setCreating] = useState(false);
  const locked = data.error?.status === 403;
  return (
    <ModuleShell
      group="banking"
      item="bank-requests"
      actions={
        locked ? undefined : (
          <>
            <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
              {v.button}
            </Button>
            <DataTools dataset="banking_cases" />
          </>
        )
      }
    >
      <p className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-ink-3">
        <Lock className="size-3.5" strokeWidth={2} aria-hidden="true" /> {SAFETY}
      </p>
      <Panel>
        {!locked && (
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto border-b border-line p-3 sm:px-5">
            {CASE_VIEWS.map((x) => (
              <Chip key={x.value} on={tab === x.value} onClick={() => setTab(x.value)}>
                {x.label}
              </Chip>
            ))}
            <span className="mx-1 w-px shrink-0 self-stretch bg-line" aria-hidden="true" />
            <Chip on={state === "open"} onClick={() => setState("open")}>
              Open
            </Chip>
            <Chip on={state === "closed"} onClick={() => setState("closed")}>
              Closed
            </Chip>
          </div>
        )}
        {locked ? <Locked /> : data.error ? <ErrorState message={data.error.message} onRetry={data.reload} /> : !data.data ? <SkeletonRows /> : data.data.length === 0 ? <EmptyState icon={Files} title="No cases here" compact /> : (
          <ul className="divide-y divide-line">
            {data.data.map((c) => (
              <CaseRow key={c.id} c={c} />
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New bank request"
        description="Account applications get the standard requirement checklist."
        fields={[{ name: "case_type", label: "Kind", type: "select", required: true, options: NEW_CASE_TYPES } as FieldDef, ...caseFields(v.newType)]}
        initial={{ case_type: v.newType, finance_status: v.finance ? "pending" : "not_needed" }}
        submitLabel="Create"
        onSubmit={async (p) => {
          const c = await post<Case>("/api/v1/banking/cases", { ...p, case_type: p.case_type ?? v.newType, finance_status: p.finance_status ?? "not_needed" });
          toast(`Created · ${c.reference}`);
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

const CARD_FIELDS: FieldDef[] = [
  { name: "custodian_id", label: "Custodian", type: "person", required: true, placeholder: "Who holds the card" },
  { name: "bank", label: "Bank", required: true, half: true },
  { name: "card_last4", label: "Last 4 digits", required: true, half: true, placeholder: "1234" },
  { name: "expiry_month", label: "Expiry month", type: "number", required: true, half: true },
  { name: "expiry_year", label: "Expiry year", type: "number", required: true, half: true },
  { name: "card_type", label: "Card type", type: "select", half: true, more: true, options: [{ value: "credit", label: "Credit" }, { value: "debit", label: "Debit" }, { value: "prepaid", label: "Prepaid" }] },
  { name: "credit_limit_php", label: "Credit limit", type: "money", half: true, more: true },
  { name: "notes", label: "Notes", type: "textarea", more: true, hint: "No card numbers, CVV or PINs" },
];

/** Corporate cards; "Expiring in 90 days" is a filter with a Start renewal action. */
export function CardsPage({ view = "all" }: { view?: "all" | "expiring" }) {
  const toast = useToast();
  const router = useRouter();
  const [tab, setTab] = useState(view);
  const renewals = tab === "expiring";
  const data = useApi<Card[]>(`/api/v1/banking/cards${renewals ? "?expiring_within=90" : ""}`);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Card | null>(null);
  const locked = data.error?.status === 403;
  async function startRenewal(c: Card) {
    try {
      const r = await post<Case>("/api/v1/banking/cases", { bank: c.bank, case_type: "card_renewal", subject: `Renew ${c.bank} ${c.card_masked} (${c.custodian.name})`, card_id: c.id, renewal_date: c.expiry_date, responsible_id: null });
      toast(`Renewal case · ${r.reference}`);
      router.push(`/bank-case/${r.id}`);
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  return (
    <ModuleShell
      group="banking"
      item="corporate-cards"
      actions={
        locked ? undefined : (
          <>
            <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
              Add card
            </Button>
            <DataTools dataset="corporate_cards" />
          </>
        )
      }
    >
      <p className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-ink-3">
        <Lock className="size-3.5" strokeWidth={2} aria-hidden="true" /> {SAFETY} Every view is logged.
      </p>
      <Panel>
        {!locked && (
          <div className="flex gap-1.5 border-b border-line p-3 sm:px-5">
            <Chip on={!renewals} onClick={() => setTab("all")}>
              All cards
            </Chip>
            <Chip on={renewals} onClick={() => setTab("expiring")}>
              Expiring in 90 days
            </Chip>
          </div>
        )}
        {locked ? <Locked /> : !data.data ? <SkeletonRows /> : data.data.length === 0 ? <EmptyState icon={CreditCard} title={renewals ? "No upcoming expiries" : "No corporate cards yet"} compact /> : (
          <ul className="divide-y divide-line">
            {data.data.map((c) => (
              <li key={c.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                <span className="flex min-w-0 flex-1 items-start gap-3.5">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line" aria-hidden="true">
                    <CreditCard className="size-5" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0">
                    <span className="tabular block text-[15px] font-bold">
                      {c.bank} {c.card_masked}
                    </span>
                    <span className="block text-[12.5px] text-ink-3">
                      {c.custodian.name} · {c.card_type} · expires {c.expiry}
                      {c.credit_limit_php ? ` · limit ${peso(c.credit_limit_php)}` : ""}
                    </span>
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2 self-start text-[12.5px] sm:self-center">
                  <DueLabel days={c.days_to_expiry} />
                  {c.status !== "active" && <span className="font-medium text-ink-3">{c.status.replace("_", " ")}</span>}
                  {renewals ? (
                    <Button size="sm" icon={RefreshCcw} onClick={() => startRenewal(c)}>
                      Start renewal
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit card" onClick={() => setEditing(c)} />
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a corporate card"
        description={SAFETY}
        fields={CARD_FIELDS}
        initial={{ card_type: "credit" }}
        submitLabel="Add card"
        onSubmit={async (p) => {
          await post("/api/v1/banking/cards", { ...p, card_type: p.card_type ?? "credit" });
          toast("Card added");
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.bank ?? ""} ${editing?.card_masked ?? ""}`}
        fields={[
          { name: "custodian_id", label: "Custodian", type: "person" },
          { name: "expiry_month", label: "Expiry month", type: "number", half: true },
          { name: "expiry_year", label: "Expiry year", type: "number", half: true },
          { name: "credit_limit_php", label: "Credit limit", type: "money", half: true },
          { name: "status", label: "Status", type: "select", half: true, options: ["active", "blocked", "cancelled", "for_renewal", "expired"].map((v) => ({ value: v, label: v.replace("_", " ") })) },
          { name: "notes", label: "Notes", type: "textarea" },
        ]}
        initial={editing ? { custodian_id: String(editing.custodian.id), expiry_month: editing.expiry.split("/")[0], expiry_year: editing.expiry.split("/")[1], credit_limit_php: editing.credit_limit_php ?? "", status: editing.status, notes: editing.notes ?? "" } : undefined}
        onSubmit={async (p) => {
          await api(`/api/v1/banking/cards/${editing!.id}`, { method: "PATCH", json: p });
          toast("Saved");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

export function BankCaseView({ id }: { id: number }) {
  const toast = useToast();
  const q = useApi<CaseDetail>(`/api/v1/banking/cases/${id}`);
  const [dialog, setDialog] = useState<null | "reject" | "cancel" | "finance_confirm" | "finance_reject">(null);
  if (q.error) return <PageFrame>{q.error.status === 403 ? <Locked /> : <ErrorState message={q.error.status === 404 ? "This case doesn't exist or isn't shared with you." : q.error.message} />}</PageFrame>;
  const c = q.data;
  if (!c) return <PageFrame><SkeletonRows /></PageFrame>;
  const open = ["open", "submitted", "approved"].includes(c.status);
  async function act(action: string, extra: Record<string, unknown> = {}) {
    try {
      q.setData({ ...c!, ...(await post<Case>(`/api/v1/banking/cases/${c!.id}/action`, { action, ...extra })) });
      toast("Updated");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  async function tick(i: number, done: boolean) {
    const before = c!;
    q.setData({ ...before, requirements: before.requirements.map((r, n) => (n === i ? { ...r, done } : r)), requirements_done: before.requirements_done + (done ? 1 : -1) });
    try {
      await api(`/api/v1/banking/cases/${before.id}/requirements`, { method: "PUT", json: { index: i, done } });
    } catch (e) {
      q.setData(before);
      toast((e as ApiError).message, "error");
    }
  }
  const ready = c.requirements.every((r) => r.done);
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Banking & Cards", href: "/banking/corporate-cards" }, { label: c.reference }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Landmark className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {c.reference} · {c.type_label} · {c.bank}
            {c.account_masked ? ` · ${c.account_masked}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">{c.subject}</h1>
          <p className="mt-2 text-[14px] text-ink-2">
            {CASE_STATUS[c.status]} · {FIN_STATUS[c.finance_status]}
            {c.finance_reference ? ` (${c.finance_reference})` : ""}
          </p>
        </div>
      </header>
      {open && (
        <section className="mt-6 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 sm:p-5">
          <ActionRow
            danger={
              <Button variant="danger" icon={Ban} onClick={() => setDialog("cancel")}>
                Cancel case
              </Button>
            }
          >
          {c.status === "open" && (
            <Button variant="primary" icon={Send} disabled={!ready} onClick={() => act("submit")}>
              {ready ? "Mark as submitted to bank" : "Complete requirements to submit"}
            </Button>
          )}
          {c.status === "submitted" && (
            <>
              <Button variant="primary" icon={Check} onClick={() => act("approve")}>
                Record bank approval
              </Button>
              <Button icon={X} onClick={() => setDialog("reject")}>
                Record bank rejection
              </Button>
            </>
          )}
          {(c.finance_status === "pending" || c.finance_status === "rejected") && (
            <Button icon={HandCoins} onClick={() => act("finance_send")}>
              Send to Finance
            </Button>
          )}
          {c.finance_status === "sent" && (
            <>
              <Button icon={Check} onClick={() => setDialog("finance_confirm")}>
                Record Finance confirmation
              </Button>
              <Button icon={X} onClick={() => setDialog("finance_reject")}>
                Record Finance rejection
              </Button>
            </>
          )}
          <Button icon={Check} disabled={["pending", "sent"].includes(c.finance_status)} onClick={() => act("complete")}>
            Complete
          </Button>
          </ActionRow>
        </section>
      )}
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Requirements" meta={`${c.requirements_done}/${c.requirements.length}`}>
            {c.requirements.length === 0 ? (
              <p className="px-4 py-3 text-[13px] text-ink-3 sm:px-5">No checklist for this case.</p>
            ) : (
              <ul className="divide-y divide-line">
                {c.requirements.map((r, i) => (
                  <li key={i}>
                    <label className={cn("flex min-h-12 items-center gap-3 px-4 sm:px-5", open && "cursor-pointer hover:bg-canvas")}>
                      <input type="checkbox" className="size-[18px] accent-[#111]" checked={r.done} disabled={!open} onChange={(e) => tick(i, e.target.checked)} />
                      <span className={cn("text-[14px]", r.done && "text-ink-3 line-through")}>{r.name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {c.notes && (
            <Panel title="Notes">
              <p className="whitespace-pre-line px-4 py-3 text-[13.5px] text-ink-2 sm:px-5">{c.notes}</p>
            </Panel>
          )}
        </div>
        <aside className="flex flex-col gap-5">
          <Panel title="Information">
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Company", c.company?.code ?? ""],
                ["Responsible", c.responsible?.name ?? "Not assigned"],
                ["Applied", c.application_date ? fmtDate(c.application_date) : ""],
                ["Renewal / due", c.renewal_date ? fmtDate(c.renewal_date) : ""],
                ["Card", c.card ? `${c.card.bank} ${c.card.card_masked}` : ""],
                ["Last updated", c.updated_at ? fmtDate(c.updated_at) : ""],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
          </Panel>
          <DocumentsPanel relatedType="banking" relatedId={c.id} />
          <RecordAttachments ownerType="banking" ownerId={c.id} items={c.attachments} canAdd={open} onChange={q.reload} />
        </aside>
      </div>
      <RecordDialog
        open={Boolean(dialog)}
        onClose={() => setDialog(null)}
        title={dialog === "finance_confirm" ? "Record Finance confirmation" : dialog === "reject" ? "Record bank rejection" : dialog === "finance_reject" ? "Record Finance rejection" : "Cancel case"}
        fields={dialog === "finance_confirm" ? [{ name: "finance_reference", label: "Finance reference", required: true }] : [{ name: "note", label: "Reason", type: "textarea", required: dialog !== "finance_reject" }]}
        onSubmit={async (p) => {
          await act(dialog!, p);
        }}
      />
    </PageFrame>
  );
}
