"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, ChevronRight, Gavel, History, Undo2, UserRoundCog, X, CalendarRange, Ban } from "lucide-react";
import { fmtDate, fmtRelative, invalidate, post, qs, useApi, type ApiError, type Page, type Person, type RequestDetail, type RequestSummary, type Step } from "@/lib/api";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { Button, Field, Input, Textarea } from "@/components/ui/controls";
import { Dialog, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { KIND_ICON, PriorityLabel, SlaLabel } from "@/components/ui/status";
import { PeoplePicker } from "@/components/requests/people-picker";
import { useShell } from "@/components/shell/shell-context";
import { INBOX } from "@/lib/nav";

type InboxItem = { step: Step; request: RequestSummary; on_behalf_of: Person | null; waiting_since: string | null };
type Delegation = { id: number; delegator: Person; delegate: Person; starts_on: string; ends_on: string; reason: string | null; state: "active" | "scheduled" | "ended" | "revoked" };

const DECISIONS = {
  approve: { title: "Approve", done: "Approved", icon: Check, field: "Comment (optional)", required: false, variant: "primary" as const },
  return: { title: "Return for changes", done: "Returned", icon: Undo2, field: "What should change?", required: true, variant: "secondary" as const },
  reject: { title: "Reject", done: "Rejected", icon: X, field: "Reason", required: true, variant: "danger" as const },
};

export function ApprovalInbox() {
  const { me, refreshMe } = useShell();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const q = useApi<Page<InboxItem>>(`/api/v1/approvals/inbox${qs({ page, page_size: 20 })}`);
  const history = useApi<{ step: Step; request: RequestSummary }[]>("/api/v1/approvals/history?limit=10");
  const [open, setOpen] = useState<{ item: InboxItem; decision: keyof typeof DECISIONS } | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function decide() {
    if (!open) return;
    setBusy(true);
    setError(undefined);
    try {
      const r = await post<RequestDetail>(`/api/v1/requests/${open.item.request.id}/actions/${open.decision}`, { message });
      toast(`${DECISIONS[open.decision].done} · ${r.reference}`);
      setOpen(null);
      setMessage("");
      invalidate();
      refreshMe();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const spec = open ? DECISIONS[open.decision] : undefined;

  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Approval Inbox" }]} />
      <PageHeader title={INBOX.label} summary="Requests waiting for your decision, oldest first. Decisions are recorded with your name and time." icon={Gavel} />
      <div className="mt-8 grid gap-5 lg:mt-10 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Waiting for you" meta={q.data ? `${q.data.total}` : undefined}>
            {q.error ? (
              <ErrorState message={q.error.status === 403 ? "You don't hold approval duties right now." : q.error.message} onRetry={q.error.status === 403 ? undefined : q.reload} />
            ) : !q.data ? (
              <SkeletonRows rows={3} />
            ) : q.data.items.length === 0 ? (
              <EmptyState icon={Check} title="You're all caught up" body="New approval requests arrive here and in your notifications." compact />
            ) : (
              <>
                <ul className="divide-y divide-line">
                  {q.data.items.map((it) => {
                    const r = it.request;
                    const Icon = KIND_ICON[r.kind];
                    return (
                      <li key={it.step.id} className="p-4 sm:px-5">
                        <Link href={`/r/${r.id}`} className="group flex items-start gap-3.5">
                          <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line bg-sheet" aria-hidden="true">
                            <Icon className="size-5" strokeWidth={1.6} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-[15px] font-bold leading-snug group-hover:underline">{r.subject}</span>
                            <span className="mt-0.5 block text-[12.5px] text-ink-3">
                              <span className="tabular">{r.reference}</span> · {r.requester.name}
                              {r.department ? `, ${r.department.name}` : ""} · {r.kind_label}
                            </span>
                            <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                              <span className="font-medium">{it.step.name}</span>
                              <span className="text-ink-3">waiting {fmtRelative(it.waiting_since).replace(" ago", "")}</span>
                              <PriorityLabel priority={r.priority} />
                              <SlaLabel sla={r.sla} />
                              {it.on_behalf_of && <span className="text-ink-2">On behalf of {it.on_behalf_of.name}</span>}
                            </span>
                          </span>
                          <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink" strokeWidth={1.75} aria-hidden="true" />
                        </Link>
                        <div className="mt-3 flex flex-wrap gap-2 sm:pl-[54px]">
                          {(Object.keys(DECISIONS) as (keyof typeof DECISIONS)[]).map((k) => (
                            <Button key={k} size="sm" variant={DECISIONS[k].variant} icon={DECISIONS[k].icon} onClick={() => (setMessage(""), setError(undefined), setOpen({ item: it, decision: k }))}>
                              {DECISIONS[k].title}
                            </Button>
                          ))}
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <Pager page={page} pageSize={20} total={q.data.total} onPage={setPage} />
              </>
            )}
          </Panel>

          <Panel title="Your recent decisions">
            {!history.data ? (
              <SkeletonRows rows={2} />
            ) : history.data.length === 0 ? (
              <EmptyState icon={History} title="No decisions yet" compact />
            ) : (
              <ul className="divide-y divide-line">
                {history.data.map(({ step, request }) => (
                  <li key={step.id}>
                    <Link href={`/r/${request.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas sm:px-5">
                      {step.status === "approved" ? <Check className="size-4 shrink-0" strokeWidth={2} aria-label="Approved" /> : step.status === "rejected" ? <X className="size-4 shrink-0 text-danger" strokeWidth={2} aria-label="Rejected" /> : <Undo2 className="size-4 shrink-0" strokeWidth={2} aria-label="Returned" />}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-medium">{request.subject}</span>
                        <span className="block text-[12.5px] text-ink-3">
                          <span className="tabular">{request.reference}</span> · {step.name} · {fmtRelative(step.decided_at)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <aside className="flex flex-col gap-5">{me?.approver && <Delegations />}</aside>
      </div>

      <Dialog
        open={Boolean(open)}
        onClose={() => setOpen(null)}
        title={`${spec?.title ?? ""} · ${open?.item.request.reference ?? ""}`}
        description={open ? `${open.item.request.subject} — ${open.item.step.name}` : undefined}
        footer={
          <>
            <Button onClick={() => setOpen(null)}>Back</Button>
            <Button variant={spec?.variant === "danger" ? "danger" : "primary"} busy={busy} disabled={Boolean(spec?.required && !message.trim())} onClick={decide}>
              {spec?.title}
            </Button>
          </>
        }
      >
        <Field label={spec?.field ?? ""} required={spec?.required} htmlFor="decision-msg" error={error}>
          <Textarea id="decision-msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
      </Dialog>
    </PageFrame>
  );
}

function Delegations() {
  const toast = useToast();
  const { me } = useShell();
  const q = useApi<{ given: Delegation[]; received: Delegation[] }>("/api/v1/approvals/delegations");
  const [open, setOpen] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const [delegate, setDelegate] = useState<number | null>(null);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError>();

  async function create() {
    setBusy(true);
    setErr(undefined);
    try {
      await post("/api/v1/approvals/delegations", { delegate_id: delegate, starts_on: from, ends_on: to, reason: reason || null });
      toast("Delegation saved");
      setOpen(false);
      q.reload();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const live = q.data?.given.filter((d) => d.state === "active" || d.state === "scheduled") ?? [];
  return (
    <Panel title="Delegation" actions={<Button size="sm" variant="ghost" icon={UserRoundCog} onClick={() => setOpen(true)}>Delegate</Button>}>
      <div className="p-4 text-[13.5px] sm:px-5">
        {live.length === 0 && !q.data?.received.some((d) => d.state === "active") && <p className="text-ink-3">Away? Let someone decide on your behalf for a set period. Every decision records who acted for whom.</p>}
        <ul className="flex flex-col gap-3">
          {live.map((d) => (
            <li key={d.id} className="flex items-start gap-3">
              <CalendarRange className="mt-0.5 size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{d.delegate.name}</span>
                <span className="block text-[12.5px] text-ink-3">
                  {fmtDate(d.starts_on)} – {fmtDate(d.ends_on)} · {d.state}
                </span>
              </span>
              <Button
                size="sm"
                variant="ghost"
                icon={Ban}
                onClick={async () => {
                  await post(`/api/v1/approvals/delegations/${d.id}/revoke`);
                  toast("Delegation revoked");
                  q.reload();
                }}
              >
                Revoke
              </Button>
            </li>
          ))}
          {q.data?.received
            .filter((d) => d.state === "active")
            .map((d) => (
              <li key={d.id} className="flex items-start gap-3">
                <UserRoundCog className="mt-0.5 size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                <span>
                  You decide for <span className="font-medium">{d.delegator.name}</span> until {fmtDate(d.ends_on)}
                </span>
              </li>
            ))}
        </ul>
      </div>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Delegate approvals"
        description="The delegate can approve, return or reject stages assigned to you during these dates."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Back</Button>
            <Button variant="primary" busy={busy} disabled={!delegate} onClick={create}>
              Save delegation
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Delegate" required htmlFor="delegate" error={err?.fields.delegate_id ? err.message : undefined}>
            <PeoplePicker id="delegate" value={delegate} onChange={setDelegate} exclude={me ? [me.employee.id] : []} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="From" htmlFor="d-from">
              <Input id="d-from" type="date" min={today} value={from} onChange={(e) => setFrom(e.target.value)} />
            </Field>
            <Field label="Until" htmlFor="d-to" error={err?.fields.ends_on ?? (err && !err.fields.delegate_id ? err.message : undefined)}>
              <Input id="d-to" type="date" min={from} value={to} onChange={(e) => setTo(e.target.value)} />
            </Field>
          </div>
          <Field label="Reason (optional)" htmlFor="d-reason">
            <Input id="d-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
      </Dialog>
    </Panel>
  );
}
