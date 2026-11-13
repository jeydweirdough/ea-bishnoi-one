"use client";

import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Copy, KeyRound, Pencil, Plus, Save, Trash2, Play, ScrollText, Search, ShieldUser, UserCog, UserPlus, User, Lock } from "lucide-react";
import { api, fmtDateTime, fmtRelative, invalidate, post, qs, useApi, type ApiError, type Page, type Person, type Priority } from "@/lib/api";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { Button, Field, Input, Select, Switch } from "@/components/ui/controls";
import { Dialog, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, type FieldDef } from "@/components/ui/record-form";
import { PRIORITY_LABEL } from "@/components/ui/status";
import { PeoplePicker } from "@/components/requests/people-picker";
import { useShell } from "@/components/shell/shell-context";
import { settingsMenu } from "@/lib/menu";
import Link from "next/link";
import { cn } from "@/lib/cn";

/** All admin setup lives behind one "Settings" door, with tabs instead of four sidebar entries. */
function Header({ href, children, actions }: { href: string; title?: string; summary?: string; children?: React.ReactNode; actions?: React.ReactNode }) {
  const { me } = useShell();
  const tabs = settingsMenu(me?.role ?? "admin");
  const current = tabs.find((t) => t.href === href);
  const copy = SETTINGS_COPY[href];
  return (
    <>
      <Breadcrumbs crumbs={[{ label: "Settings", href: tabs[0]?.href }, { label: current?.label ?? copy.title }]} />
      <PageHeader title={current?.label ?? copy.title} summary={copy.summary} icon={iconForHref(href)} actions={actions}>
        {children}
      </PageHeader>
      {tabs.length > 1 && (
        <nav aria-label="Settings" className="no-scrollbar -mx-4 mt-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <ul className="flex min-w-max gap-1 border-b border-line">
            {tabs.map((t) => {
              const on = t.href === href;
              return (
                <li key={t.href}>
                  <Link
                    href={t.href}
                    aria-current={on ? "page" : undefined}
                    className={cn(
                      "-mb-px flex h-11 items-center gap-2 border-b-2 px-3 text-[14px] transition-colors duration-150",
                      on ? "border-ink font-bold text-ink" : "border-transparent font-medium text-ink-3 hover:text-ink",
                    )}
                  >
                    <t.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
                    {t.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </>
  );
}

const SETTINGS_COPY: Record<string, { title: string; summary: string }> = {
  "/administration/approvals": { title: "Approval routes", summary: "Who approves each type of request, in order." },
  "/administration/priorities-sla": { title: "Deadlines (SLA)", summary: "How fast each priority must be answered and resolved." },
  "/administration/audit-logs": { title: "Audit log", summary: "Every change, decision and download. Nothing here can be edited." },
  "/administration/settings": { title: "People & access", summary: "Who can sign in, who can approve, and what Assistants and staff may do." },
};

/* ================================================================ workflows */

type Stage = { id?: number; name: string; approver_type: "employee" | "department_head"; approver: Person | null; approver_id?: number | null; active: boolean; min_priority: Priority | null };
type Template = { id: number; key: string; name: string; description: string | null; kinds: string[]; processing: string[]; active: boolean; updated_at: string; stages: Stage[] };

const KIND_LABEL: Record<string, string> = {
  concern: "Concerns",
  repair: "Repairs & maintenance",
  other: "Other requests",
  supplies: "Supplies",
  asset: "Assets & equipment",
  local_purchase: "Local purchases",
};

export function WorkflowsPage({ summary }: { summary: string }) {
  const q = useApi<Template[]>("/api/v1/admin/workflows");
  return (
    <PageFrame>
      <Header href="/administration/approvals" title="Approvals" summary={summary} />
      <p className="mt-5 max-w-[64ch] text-[13.5px] leading-relaxed text-ink-3">Changes apply to new requests only. Requests already in approval keep their route.</p>
      <div className="mt-8 flex flex-col gap-5 lg:mt-10">
        {q.error ? <ErrorState message={q.error.message} onRetry={q.reload} /> : !q.data ? <Panel><SkeletonRows rows={3} /></Panel> : q.data.map((t) => <TemplateEditor key={t.id} t={t} onSaved={q.reload} />)}
      </div>
    </PageFrame>
  );
}

function TemplateEditor({ t, onSaved }: { t: Template; onSaved: () => void }) {
  const { me } = useShell();
  const toast = useToast();
  const admin = me?.role === "admin";
  const [stages, setStages] = useState<Stage[]>(t.stages.map((s) => ({ ...s, approver_id: s.approver?.id ?? null })));
  const [kinds, setKinds] = useState<string[]>(t.kinds);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError>();

  const update = (i: number, patch: Partial<Stage>) => {
    setStages((cur) => cur.map((s, j) => (j === i ? { ...s, ...patch } : s)));
    setDirty(true);
  };
  const move = (i: number, d: -1 | 1) => {
    setStages((cur) => {
      const next = [...cur];
      [next[i], next[i + d]] = [next[i + d], next[i]];
      return next;
    });
    setDirty(true);
  };

  async function save() {
    setBusy(true);
    setErr(undefined);
    try {
      await api(`/api/v1/admin/workflows/${t.id}`, {
        method: "PUT",
        json: {
          name: t.name,
          description: t.description,
          kinds,
          active: t.active,
          stages: stages.map((s) => ({ name: s.name, approver_type: s.approver_type, approver_id: s.approver_type === "employee" ? s.approver_id : null, active: s.active, min_priority: s.min_priority })),
        },
      });
      toast(`Saved · ${t.name}`);
      setDirty(false);
      onSaved();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title={t.name} meta={`Updated ${fmtDateTime(t.updated_at)}`}>
      <div className="border-b border-line p-4 sm:px-5">
        <p className="text-[12.5px] font-medium text-ink-3">Used for</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {Object.keys(KIND_LABEL).map((k) => {
            const on = kinds.includes(k);
            return (
              <button
                key={k}
                type="button"
                disabled={!admin}
                aria-pressed={on}
                onClick={() => (setKinds((cur) => (on ? cur.filter((x) => x !== k) : [...cur, k])), setDirty(true))}
                className={cn("h-9 rounded-full border px-3 text-[13px] font-medium transition-colors duration-150 disabled:cursor-default", on ? "border-ink bg-ink text-white" : "border-line bg-sheet text-ink-3 hover:text-ink")}
              >
                {KIND_LABEL[k]}
              </button>
            );
          })}
        </div>
        {err?.fields.kinds && <p className="mt-2 text-[12.5px] text-danger">{err.fields.kinds}</p>}
      </div>
      <ol className="divide-y divide-line">
        {stages.map((s, i) => (
          <li key={s.id ?? `new-${i}`} className={cn("grid gap-3 p-4 sm:px-5 md:grid-cols-[28px_minmax(0,0.8fr)_minmax(0,1.6fr)_150px_auto] md:items-end", !s.active && "bg-canvas")}>
            <span className="tabular flex size-7 items-center justify-center self-center rounded-full bg-ink text-[12px] font-bold text-white md:mb-1.5">{i + 1}</span>
            <Field label="Stage name" htmlFor={`sn-${t.id}-${i}`}>
              <Input id={`sn-${t.id}-${i}`} value={s.name} disabled={!admin} onChange={(e) => update(i, { name: e.target.value })} />
            </Field>
            <Field label="Approver" htmlFor={`sa-${t.id}-${i}`} error={err?.fields[`stages.${i}.approver_id`]}>
              <div className="grid grid-cols-[132px_minmax(0,1fr)] gap-2">
                <Select aria-label="Approver type" value={s.approver_type} disabled={!admin} onChange={(e) => update(i, { approver_type: e.target.value as Stage["approver_type"] })}>
                  <option value="department_head">Dept. head</option>
                  <option value="employee">Person</option>
                </Select>
                {s.approver_type === "employee" ? (
                  admin ? (
                    <PeoplePicker id={`sa-${t.id}-${i}`} value={s.approver_id ?? null} onChange={(v) => update(i, { approver_id: v })} approvers invalid={Boolean(err?.fields[`stages.${i}.approver_id`])} />
                  ) : (
                    <Input id={`sa-${t.id}-${i}`} disabled value={s.approver?.name ?? "—"} />
                  )
                ) : (
                  <Input id={`sa-${t.id}-${i}`} disabled value="Requester's department head" />
                )}
              </div>
            </Field>
            <Field label="Applies when" htmlFor={`sp-${t.id}-${i}`}>
              <Select id={`sp-${t.id}-${i}`} value={s.min_priority ?? ""} disabled={!admin} onChange={(e) => update(i, { min_priority: (e.target.value || null) as Priority | null })}>
                <option value="">Always</option>
                <option value="normal">Normal or higher</option>
                <option value="high">High or critical</option>
                <option value="critical">Critical only</option>
              </Select>
            </Field>
            {admin && (
              <div className="flex items-center gap-1 md:mb-0.5">
                <label className="mr-1 flex h-10 items-center gap-2 text-[13px] text-ink-2">
                  <input type="checkbox" checked={s.active} onChange={(e) => update(i, { active: e.target.checked })} className="size-4 accent-[#111]" />
                  On
                </label>
                <IconBtn label="Move up" disabled={i === 0} onClick={() => move(i, -1)} icon={ArrowUp} />
                <IconBtn label="Move down" disabled={i === stages.length - 1} onClick={() => move(i, 1)} icon={ArrowDown} />
                <IconBtn label="Remove stage" onClick={() => (setStages((cur) => cur.filter((_, j) => j !== i)), setDirty(true))} icon={Trash2} />
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="flex flex-col gap-3 border-t border-line p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <p className="text-[12.5px] text-ink-3">After approval: {t.processing.join(" → ")}</p>
        {admin ? (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" icon={Plus} disabled={stages.length >= 12} onClick={() => (setStages((cur) => [...cur, { name: "New stage", approver_type: "employee", approver: null, approver_id: null, active: true, min_priority: null }]), setDirty(true))}>
              Add stage
            </Button>
            <Button size="sm" variant="primary" icon={Save} busy={busy} disabled={!dirty} onClick={save}>
              Save route
            </Button>
          </div>
        ) : (
          <p className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-3">
            <Lock className="size-3.5" aria-hidden="true" /> Only Admin can change routes
          </p>
        )}
      </div>
      {err && !Object.keys(err.fields).length && <p className="px-5 pb-4 text-[13px] text-danger">{err.message}</p>}
    </Panel>
  );
}

function IconBtn({ label, icon: Icon, onClick, disabled }: { label: string; icon: typeof ArrowUp; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" aria-label={label} title={label} disabled={disabled} onClick={onClick} className="flex size-10 items-center justify-center rounded-[var(--radius-ctl)] text-ink-3 hover:bg-hover hover:text-ink disabled:opacity-30">
      <Icon className="size-4" strokeWidth={1.75} />
    </button>
  );
}

/* ================================================================ SLA */

type Sla = { priority: Priority; response_hours: number; resolution_hours: number; escalate_every_hours: number; default_assignee: Person | null; updated_at: string };

export function SlaPage({ summary }: { summary: string }) {
  const toast = useToast();
  const q = useApi<Sla[]>("/api/v1/admin/sla");
  const [running, setRunning] = useState(false);
  return (
    <PageFrame>
      <Header href="/administration/priorities-sla" title="Priorities & SLA" summary={summary}>
        <div className="mt-5">
          <Button
            icon={Play}
            busy={running}
            onClick={async () => {
              setRunning(true);
              try {
                const r = await post<{ escalated: number }>("/api/v1/admin/escalations/run");
                toast(r.escalated ? `Escalated ${r.escalated} overdue ${r.escalated === 1 ? "request" : "requests"}` : "No new escalations");
                invalidate();
              } catch (e) {
                toast((e as ApiError).message, "error");
              } finally {
                setRunning(false);
              }
            }}
          >
            Run escalation check now
          </Button>
        </div>
      </Header>
      <p className="mt-5 max-w-[64ch] text-[13.5px] leading-relaxed text-ink-3">The clock starts when a request is sent. Overdue requests alert Admin and the owner automatically.</p>
      <div className="mt-8 lg:mt-10">
        {q.error ? <ErrorState message={q.error.message} onRetry={q.reload} /> : !q.data ? <Panel><SkeletonRows rows={4} /></Panel> : (
          <div className="grid gap-4 md:grid-cols-2">
            {q.data.map((p) => (
              <SlaCard key={p.priority} p={p} />
            ))}
          </div>
        )}
      </div>
    </PageFrame>
  );
}

function SlaCard({ p }: { p: Sla }) {
  const toast = useToast();
  const [resp, setResp] = useState(String(p.response_hours));
  const [res, setRes] = useState(String(p.resolution_hours));
  const [every, setEvery] = useState(String(p.escalate_every_hours));
  const [owner, setOwner] = useState<number | null>(p.default_assignee?.id ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError>();
  const dirty = resp !== String(p.response_hours) || res !== String(p.resolution_hours) || every !== String(p.escalate_every_hours) || owner !== (p.default_assignee?.id ?? null);

  async function save() {
    setBusy(true);
    setErr(undefined);
    try {
      await api(`/api/v1/admin/sla/${p.priority}`, { method: "PUT", json: { response_hours: Number(resp), resolution_hours: Number(res), escalate_every_hours: Number(every), default_assignee_id: owner } });
      toast(`${PRIORITY_LABEL[p.priority]} SLA saved`);
      invalidate();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const hours = (v: string, set: (s: string) => void, id: string, label: string, fieldKey: string) => (
    <Field label={label} htmlFor={id} error={err?.fields[fieldKey]}>
      <div className="relative">
        <Input id={id} inputMode="numeric" className="tabular pr-12" value={v} onChange={(e) => set(e.target.value.replace(/[^0-9]/g, ""))} />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[13px] text-ink-3">hrs</span>
      </div>
    </Field>
  );

  return (
    <Panel title={PRIORITY_LABEL[p.priority]} meta={`Updated ${fmtDateTime(p.updated_at)}`}>
      <div className="grid gap-4 p-4 sm:grid-cols-3 sm:px-5">
        {hours(resp, setResp, `r-${p.priority}`, "First response", "response_hours")}
        {hours(res, setRes, `s-${p.priority}`, "Resolution", "resolution_hours")}
        {hours(every, setEvery, `e-${p.priority}`, "Re-escalate every", "escalate_every_hours")}
        <Field label="Default owner after approval" htmlFor={`o-${p.priority}`} className="sm:col-span-3" hint="Priority-based assignment. Leave empty to assign manually." error={err?.fields.default_assignee_id}>
          <PeoplePicker id={`o-${p.priority}`} value={owner} onChange={setOwner} role={["admin", "assistant"]} placeholder="No automatic owner" />
        </Field>
        {err && !Object.keys(err.fields).length && <p className="text-[13px] text-danger sm:col-span-3">{err.message}</p>}
      </div>
      <div className="flex justify-end border-t border-line p-3 sm:px-5">
        <Button size="sm" variant="primary" icon={Save} busy={busy} disabled={!dirty || !resp || !res || !every} onClick={save}>
          Save
        </Button>
      </div>
    </Panel>
  );
}

/* ================================================================ audit */

type AuditRow = { id: number; at: string; actor: Person | null; action: string; entity_type: string; entity_id: number | null; entity_ref: string | null; data: Record<string, unknown> };

const AUDIT_FILTERS = [
  { value: "", label: "All events" },
  { value: "request", label: "Requests" },
  { value: "approval", label: "Approvals" },
  { value: "attachment", label: "Attachments" },
  { value: "task", label: "Tasks" },
  { value: "workflow", label: "Workflow changes" },
  { value: "sla", label: "SLA" },
  { value: "access", label: "Access grants" },
];

export function AuditPage({ summary }: { summary: string }) {
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => setTerm(q), 250);
    return () => clearTimeout(t);
  }, [q]);
  const data = useApi<Page<AuditRow>>(`/api/v1/admin/audit${qs({ action, q: term, date_from: from, date_to: to, page, page_size: 50 })}`);
  return (
    <PageFrame>
      <Header href="/administration/audit-logs" title="Audit Logs" summary={summary} />

      <div className="mt-8 lg:mt-10">
        <Panel>
          <div className="grid gap-2 border-b border-line p-3 sm:grid-cols-[minmax(0,1fr)_180px_150px_150px] sm:px-5">
            <label className="relative">
              <span className="sr-only">Search reference or action</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
              <Input type="search" placeholder="Reference or action" className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
            </label>
            <Select aria-label="Event type" value={action} onChange={(e) => (setAction(e.target.value), setPage(1))}>
              {AUDIT_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
            <Input aria-label="From date" type="date" value={from} onChange={(e) => (setFrom(e.target.value), setPage(1))} />
            <Input aria-label="To date" type="date" value={to} onChange={(e) => (setTo(e.target.value), setPage(1))} />
          </div>
          {data.error ? (
            <ErrorState message={data.error.message} onRetry={data.reload} />
          ) : !data.data ? (
            <SkeletonRows />
          ) : data.data.items.length === 0 ? (
            <EmptyState icon={ScrollText} title="No events match" compact />
          ) : (
            <>
              <ul className="divide-y divide-line">
                {data.data.items.map((a) => (
                  <li key={a.id} className="grid gap-1 px-4 py-3 text-[13.5px] sm:grid-cols-[150px_minmax(0,1fr)_minmax(0,1.2fr)] sm:gap-4 sm:px-5">
                    <time className="tabular text-[12.5px] text-ink-3" dateTime={a.at}>
                      {fmtDateTime(a.at)}
                    </time>
                    <span className="min-w-0">
                      <span className="block font-medium">{a.action}</span>
                      <span className="block text-[12.5px] text-ink-3">
                        {a.actor?.name ?? "System"}
                        {a.entity_ref ? ` · ${a.entity_ref}` : ""}
                      </span>
                    </span>
                    <span className="tabular min-w-0 truncate text-[12.5px] text-ink-3" title={JSON.stringify(a.data)}>
                      {Object.entries(a.data)
                        .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
                        .join(" · ") || "—"}
                    </span>
                  </li>
                ))}
              </ul>
              <Pager page={page} pageSize={50} total={data.data.total} onPage={setPage} />
            </>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

/* ================================================================ settings (access grants) */

type Grant = Person & {
  role: "admin" | "assistant" | "employee";
  company: string;
  company_id: number;
  department_id: number | null;
  email: string | null;
  active: boolean;
  can_approve: boolean;
  delegations: { assign?: boolean; set_priority?: boolean; travel_documents?: boolean; banking?: boolean; inventory_adjust?: boolean };
  company_access: string[];
  sign_in: { has_password: boolean; must_change_password: boolean; locked: boolean; last_login_at: string | null };
};
type Company = { id: number; code: string; name: string };

const ROLE_OPTIONS = [
  { value: "employee", label: "Employee" },
  { value: "assistant", label: "Assistant" },
  { value: "admin", label: "Admin" },
];

function accountFields(companies: Company[] | undefined, edit = false): FieldDef[] {
  return [
    { name: "name", label: "Full name", required: true },
    { name: "email", label: "Work email", required: true, half: true, hint: "Used to sign in" },
    { name: "designation", label: "Position", half: true, placeholder: "e.g. Sales Associate" },
    { name: "role", label: "User type", type: "select", required: true, half: true, options: ROLE_OPTIONS },
    { name: "company_id", label: "Company", type: "select", required: true, half: true, options: (companies ?? []).map((c) => ({ value: String(c.id), label: `${c.name} (${c.code})` })) },
    { name: "department_id", label: "Department", type: "department", half: true },
    ...(edit ? [{ name: "active", label: "Status", type: "select", required: true, half: true, options: [{ value: "true", label: "Active" }, { value: "false", label: "Deactivated (cannot sign in)" }] } as FieldDef] : []),
  ];
}

function accountPayload(p: Record<string, unknown>) {
  return {
    ...p,
    company_id: p.company_id ? Number(p.company_id) : undefined,
    department_id: p.department_id ? Number(p.department_id) : null,
    ...(p.active !== undefined ? { active: p.active === "true" || p.active === true } : {}),
  };
}

/** Shows a one-time temporary password with a copy button. It is not stored in readable form anywhere. */
function TemporaryPassword({ shown, onClose }: { shown: { name: string; email: string | null; password: string } | null; onClose: () => void }) {
  const toast = useToast();
  return (
    <Dialog
      open={Boolean(shown)}
      onClose={onClose}
      title="Temporary password"
      description={shown ? `For ${shown.name}. Shown only once.` : undefined}
      footer={
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      }
    >
      {shown && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2 rounded-[var(--radius-ctl)] border border-line bg-canvas p-3">
            <code className="tabular flex-1 select-all break-all font-mono text-[20px] font-bold tracking-wide">{shown.password}</code>
            <Button
              size="sm"
              icon={Copy}
              onClick={() => {
                void navigator.clipboard?.writeText(shown.password);
                toast("Copied");
              }}
            >
              Copy
            </Button>
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-[13.5px] leading-relaxed text-ink-2">
            <li>
              Give it to {shown.name} in person or by a private message. They sign in at <b>ea.bishnoi.ai</b> with <b>{shown.email}</b>.
            </li>
            <li>They must choose their own password right after signing in.</li>
            <li>It can&rsquo;t be shown again. If it&rsquo;s lost, issue a new one.</li>
          </ol>
        </div>
      )}
    </Dialog>
  );
}


const ROLE_ICON = { admin: ShieldUser, assistant: UserCog, employee: User };

export function SettingsPage({ summary }: { summary: string }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const data = useApi<Grant[]>(`/api/v1/admin/users${qs({ q })}`);
  const companies = useApi<Company[]>("/api/v1/admin/companies");
  const [adding, setAdding] = useState(false);
  const [shown, setShown] = useState<{ name: string; email: string | null; password: string } | null>(null);
  return (
    <PageFrame>
      <Header
        href="/administration/settings"
        title="Settings"
        summary={summary}
        actions={
          <Button variant="primary" icon={UserPlus} onClick={() => setAdding(true)}>
            Add person
          </Button>
        }
      />
      <p className="mt-5 max-w-[64ch] text-[13.5px] leading-relaxed text-ink-3">
        Everyone who signs in to Executive Admin is listed here. Add a person to give them an account; they sign in with their work email. When One Admin sign-in is connected, these accounts move to it.
      </p>
      <div className="mt-8 lg:mt-10">
        <Panel title="People & access" meta={data.data ? `${data.data.length} people` : undefined}>
          <div className="border-b border-line p-3 sm:px-5">
            <label className="relative block">
              <span className="sr-only">Search people</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
              <Input type="search" placeholder="Search name, email or employee number" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
          </div>
          {data.error ? <ErrorState message={data.error.message} onRetry={data.reload} /> : !data.data ? <SkeletonRows /> : (
            <ul className="divide-y divide-line">
              {data.data.map((g) => (
                <GrantRow key={`${g.id}-${g.role}-${g.active}`} g={g} companies={companies.data} onPassword={setShown} />
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <RecordDialog
        open={adding}
        onClose={() => setAdding(false)}
        title="Add a person"
        description="They get a one-time temporary password and choose their own at first sign-in."
        fields={accountFields(companies.data)}
        initial={{ role: "employee", company_id: companies.data?.[0] ? String(companies.data[0].id) : "" }}
        submitLabel="Add person"
        onSubmit={async (p) => {
          const g = await api<Grant & { temporary_password: string }>("/api/v1/admin/users", { method: "POST", json: accountPayload(p) });
          toast(`Added ${g.name}`);
          invalidate();
          setShown({ name: g.name, email: g.email, password: g.temporary_password });
        }}
      />
      <TemporaryPassword shown={shown} onClose={() => setShown(null)} />
      <DepartmentsPanel companies={companies.data} />
    </PageFrame>
  );
}

type Dept = { id: number; code: string; name: string; company: { id: number; code: string }; head: Person | null };

/** Departments and their heads. A head approves the "Department Head" stage of every route. */
function DepartmentsPanel({ companies }: { companies?: Company[] }) {
  const toast = useToast();
  const data = useApi<Dept[]>("/api/v1/admin/departments");
  const [adding, setAdding] = useState(false);
  async function setHead(d: Dept, headId: number | null) {
    try {
      await api(`/api/v1/admin/departments/${d.id}`, { method: "PATCH", json: { head_id: headId } });
      toast(headId ? `Head of ${d.name} set` : `${d.name} has no head now`);
      data.reload();
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  const noHead = data.data?.filter((d) => !d.head).length ?? 0;
  return (
    <div className="mt-6">
      <Panel
        title="Departments"
        meta={data.data ? (noHead ? `${noHead} without a head` : `${data.data.length}`) : undefined}
        actions={
          <Button size="sm" variant="ghost" icon={Plus} onClick={() => setAdding(true)}>
            Add department
          </Button>
        }
      >
        <p className="border-b border-line px-4 py-3 text-[13px] leading-relaxed text-ink-3 sm:px-5">
          The head approves the &ldquo;Department Head&rdquo; step for requests from their department. Choosing a head turns on their approval duties.
        </p>
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows rows={3} />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.map((d) => (
              <li key={d.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] sm:items-center sm:gap-6 sm:px-5">
                <span className="min-w-0">
                  <span className="block text-[14.5px] font-bold">{d.name}</span>
                  <span className={cn("block text-[12.5px]", d.head ? "text-ink-3" : "font-medium text-danger")}>
                    {d.company.code} · {d.head ? `Head: ${d.head.name}` : "No head yet: requests stop at this step"}
                  </span>
                </span>
                <PeoplePicker id={`head-${d.id}`} value={d.head?.id ?? null} onChange={(id) => setHead(d, id)} placeholder="Choose the head" />
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={adding}
        onClose={() => setAdding(false)}
        title="Add a department"
        fields={[
          { name: "company_id", label: "Company", type: "select", required: true, options: (companies ?? []).map((c) => ({ value: String(c.id), label: `${c.name} (${c.code})` })) },
          { name: "name", label: "Department name", required: true, placeholder: "e.g. Human Resources" },
        ]}
        initial={{ company_id: companies?.[0] ? String(companies[0].id) : "" }}
        submitLabel="Add department"
        onSubmit={async (p) => {
          await api("/api/v1/admin/departments", { method: "POST", json: { ...p, company_id: Number(p.company_id) } });
          toast("Department added");
          data.reload();
          invalidate();
        }}
      />
    </div>
  );
}

const COMPANIES = ["GPI", "2MG"];

function GrantRow({ g, companies, onPassword }: { g: Grant; companies?: Company[]; onPassword: (x: { name: string; email: string | null; password: string }) => void }) {
  const toast = useToast();
  const { me } = useShell();
  const [editing, setEditing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const fields = accountFields(companies, true);
  async function issuePassword() {
    try {
      const r = await api<Grant & { temporary_password: string }>(`/api/v1/admin/users/${g.id}/temporary-password`, { method: "POST" });
      setConfirmReset(false);
      invalidate();
      onPassword({ name: g.name, email: g.email, password: r.temporary_password });
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  const signIn = !g.active
    ? "Deactivated"
    : g.sign_in.locked
      ? "Locked after wrong passwords"
      : !g.sign_in.has_password
        ? "No sign-in yet"
        : g.sign_in.must_change_password
          ? "Temporary password not yet changed"
          : g.sign_in.last_login_at
            ? `Last signed in ${fmtRelative(g.sign_in.last_login_at)}`
            : "Has not signed in yet";
  const [state, setState] = useState({ can_approve: g.can_approve, assign: Boolean(g.delegations.assign), set_priority: Boolean(g.delegations.set_priority), travel_documents: Boolean(g.delegations.travel_documents), banking: Boolean(g.delegations.banking), inventory_adjust: Boolean(g.delegations.inventory_adjust), company_access: g.company_access });
  const [busy, setBusy] = useState(false);
  const Icon = ROLE_ICON[g.role];
  const staff = g.role !== "employee";

  async function save(next: typeof state) {
    setState(next);
    setBusy(true);
    try {
      await api(`/api/v1/admin/users/${g.id}/grants`, { method: "PUT", json: next });
      toast(`Updated ${g.name}`);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
      setState(state);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={cn("grid gap-3 px-4 py-4 sm:px-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:gap-6", !g.active && "opacity-60")}>
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line bg-sheet" aria-hidden="true">
          <Icon className="size-5" strokeWidth={1.6} />
        </span>
        <span className="min-w-0">
          <span className="block text-[14.5px] font-bold">{g.name}</span>
          <span className="block text-[12.5px] text-ink-3">
            {g.role[0].toUpperCase() + g.role.slice(1)} · {g.designation ?? "—"} · <span className="tabular">{g.employee_no}</span>
          </span>
          <span className="block truncate text-[12.5px] text-ink-2">{g.email ?? "No email (cannot sign in)"}</span>
          <span className={cn("mt-0.5 block text-[12.5px]", g.sign_in.locked ? "font-medium text-danger" : "text-ink-3")}>{signIn}</span>
          <span className="mt-2 flex flex-wrap gap-1.5">
            <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing(true)} className="-ml-2">
              Edit
            </Button>
            {g.email && g.active && g.id !== me?.employee.id && (
              <Button size="sm" variant="ghost" icon={KeyRound} onClick={() => setConfirmReset(true)}>
                {g.sign_in.has_password ? "New temporary password" : "Create sign-in"}
              </Button>
            )}
          </span>
        </span>
      </div>
      <div className={cn("flex flex-col gap-1", busy && "opacity-60")}>
        <Switch checked={state.can_approve} onChange={(v) => save({ ...state, can_approve: v })} label="Approval duties" hint="Can be named as an approver in routes" />
        {g.role === "assistant" && (
          <>
            <Switch checked={state.assign} onChange={(v) => save({ ...state, assign: v })} label="Assign requests and tasks" hint="Delegated by Admin" />
            <Switch checked={state.set_priority} onChange={(v) => save({ ...state, set_priority: v })} label="Set effective priority" hint="Delegated by Admin" />
            <Switch checked={state.travel_documents} onChange={(v) => save({ ...state, travel_documents: v })} label="Passports and visas" hint="Sensitive. Every view is logged." />
            <Switch checked={state.banking} onChange={(v) => save({ ...state, banking: v })} label="Banking and corporate cards" hint="Restricted. Every view is logged." />
            <Switch checked={state.inventory_adjust} onChange={(v) => save({ ...state, inventory_adjust: v })} label="Inventory control" hint="Set up items, adjust counts, post physical counts" />
          </>
        )}
        {staff && g.active && (
          <div className="flex flex-wrap items-center gap-2 pt-1.5">
            <span className="text-[13px] text-ink-3">Companies</span>
            {COMPANIES.map((c) => {
              const on = state.company_access.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={on}
                  onClick={() => save({ ...state, company_access: on ? state.company_access.filter((x) => x !== c) : [...state.company_access, c] })}
                  className={cn("h-8 rounded-full border px-3 text-[12.5px] font-medium", on ? "border-ink bg-ink text-white" : "border-line text-ink-3 hover:text-ink")}
                >
                  {c}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <RecordDialog
        open={editing}
        onClose={() => setEditing(false)}
        title={`Edit ${g.name}`}
        description="Changing the user type or deactivating signs them out everywhere at once."
        fields={fields}
        initial={{ name: g.name, email: g.email ?? "", designation: g.designation ?? "", role: g.role, company_id: String(g.company_id), department_id: g.department_id ? String(g.department_id) : "", active: String(g.active) }}
        onSubmit={async (p) => {
          await api(`/api/v1/admin/users/${g.id}`, { method: "PATCH", json: accountPayload(p) });
          toast(`Saved ${g.name}`);
          invalidate();
        }}
      />
      <Dialog
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title={g.sign_in.has_password ? "Issue a new temporary password?" : "Create a sign-in?"}
        description={g.sign_in.has_password ? `${g.name}'s current password stops working and they are signed out everywhere. A locked account is unlocked.` : `${g.name} gets a temporary password for ${g.email}.`}
        footer={
          <>
            <Button onClick={() => setConfirmReset(false)}>Back</Button>
            <Button variant="primary" icon={KeyRound} onClick={issuePassword}>
              {g.sign_in.has_password ? "Issue new password" : "Create sign-in"}
            </Button>
          </>
        }
      />
    </li>
  );
}

