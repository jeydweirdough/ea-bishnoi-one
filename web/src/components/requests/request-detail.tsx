"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Ban,
  Check,
  ChevronDown,
  CircleCheck,
  Download,
  Flag,
  Landmark,
  LoaderCircle,
  Lock,
  MessageSquare,
  PackageCheck,
  Paperclip,
  Pencil,
  Play,
  RotateCcw,
  Send,
  Trash2,
  Undo2,
  UserCog,
  UserPlus,
  X,
} from "lucide-react";
import { api, fmtDate, fmtDateTime, fmtRelative, fmtSize, invalidate, post, useApi, type ApiError, type Priority, type RequestDetail as Detail } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Field, Segmented, Switch, Textarea, buttonClass } from "@/components/ui/controls";
import { Dialog, ErrorState, Panel, useToast } from "@/components/ui/feedback";
import { KIND_ICON, PRIORITY_LABEL, PriorityLabel, SlaLabel, StatusBadge } from "@/components/ui/status";
import { useShell } from "@/components/shell/shell-context";
import { ApprovalRoute } from "./approval-route";
import { DocumentsPanel } from "@/components/documents/documents";
import { PeoplePicker } from "./people-picker";
import { cn } from "@/lib/cn";

type ActionSpec = {
  label: string;
  icon: typeof Check;
  variant?: "primary" | "secondary" | "danger";
  dialog?: { title: string; description?: string; field?: string; required?: boolean; confirm: string };
};

const DONE_LABEL: Record<string, string> = { assign: "Owner set", set_priority: "Priority updated", reassign_step: "Approver changed" };

const SPECS: Record<string, ActionSpec> = {
  submit: { label: "Submit", icon: Send, variant: "primary" },
  approve: { label: "Approve", icon: Check, variant: "primary", dialog: { title: "Approve this stage", field: "Comment (optional)", confirm: "Approve" } },
  return: {
    label: "Return for changes",
    icon: Undo2,
    dialog: { title: "Return for changes", description: "The requester can edit and resubmit. Say what needs to change.", field: "What should change?", required: true, confirm: "Return" },
  },
  reject: {
    label: "Reject",
    icon: X,
    variant: "danger",
    dialog: { title: "Reject this request", description: "This ends the request. The requester sees your reason.", field: "Reason", required: true, confirm: "Reject" },
  },
  withdraw: { label: "Withdraw", icon: Ban, variant: "danger", dialog: { title: "Withdraw this request?", description: "Approvers stop seeing it. This cannot be undone.", field: "Reason (optional)", confirm: "Withdraw" } },
  confirm: { label: "Confirm received / resolved", icon: CircleCheck, variant: "primary", dialog: { title: "Confirm and close", description: "Closes the request.", field: "Note (optional)", confirm: "Confirm" } },
  start: { label: "Start processing", icon: Play, variant: "primary" },
  await_finance: { label: "Hand to Finance", icon: Landmark, dialog: { title: "Hand to Finance", description: "Finance owns payment. You'll record their confirmation here.", field: "Finance reference or note (optional)", confirm: "Hand off" } },
  finance_done: { label: "Record Finance confirmation", icon: Check, variant: "primary", dialog: { title: "Record Finance payment confirmation", field: "Payment reference (optional)", confirm: "Record" } },
  fulfill: { label: "Mark fulfilled", icon: PackageCheck, variant: "primary", dialog: { title: "Mark as fulfilled", description: "The requester is asked to confirm.", field: "What was delivered or resolved?", required: true, confirm: "Mark fulfilled" } },
  close: { label: "Close", icon: Lock, dialog: { title: "Close without requester confirmation", field: "Note (optional)", confirm: "Close" } },
  reopen: { label: "Reopen", icon: RotateCcw, dialog: { title: "Reopen", field: "Why is it being reopened?", required: true, confirm: "Reopen" } },
  cancel: { label: "Cancel request", icon: Ban, variant: "danger", dialog: { title: "Cancel this request", field: "Reason", required: true, confirm: "Cancel request" } },
};

const PRIMARY_ORDER = ["approve", "return", "reject", "submit", "confirm", "start", "fulfill", "finance_done", "await_finance", "close", "reopen", "withdraw"];

function nextStepCopy(d: Detail, owner: boolean): { title: string; body?: string } {
  const step = d.current_step;
  switch (d.status) {
    case "draft":
      return { title: "Draft — not sent yet", body: "Only you can see it. Submit when it's ready." };
    case "submitted":
    case "under_review":
      return {
        title: step?.approver ? `With ${step.approver.name} for approval` : "Waiting for an approver",
        body: step ? `${step.name} · stage ${d.steps_done + 1} of ${d.steps_total}` : undefined,
      };
    case "returned": {
      const s = d.steps.find((x) => x.status === "returned");
      return { title: owner ? "Changes requested" : "Returned to the requester", body: s?.comment ? `${s.decided_by?.name ?? "Approver"}: “${s.comment}”` : undefined };
    }
    case "approved":
      return { title: "Approved", body: d.assigned_to ? `${d.assigned_to.name} will process it.` : "Executive Admin will process it." };
    case "in_progress":
      return { title: "Executive Admin is working on it", body: d.assigned_to ? `Owner: ${d.assigned_to.name}` : undefined };
    case "awaiting_finance":
      return { title: "Waiting for Finance", body: "Finance owns payment; Executive Admin records the confirmation." };
    case "fulfilled":
      return { title: owner ? "Please confirm" : "Fulfilled — waiting for the requester", body: owner ? "Check that you received it or that it's resolved." : undefined };
    case "rejected":
      return { title: "Rejected", body: d.steps.find((x) => x.status === "rejected")?.comment ?? undefined };
    case "closed":
      return { title: "Closed", body: d.closed_at ? fmtDateTime(d.closed_at) : undefined };
    case "cancelled":
      return { title: "Cancelled", body: d.closed_at ? fmtDateTime(d.closed_at) : undefined };
  }
}

export function RequestDetailView({ id }: { id: number }) {
  const router = useRouter();
  const toast = useToast();
  const { me } = useShell();
  const q = useApi<Detail>(`/api/v1/requests/${id}`);
  const [dialog, setDialog] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [assignee, setAssignee] = useState<number | null>(null);
  const [priority, setPriority] = useState<Priority>("normal");
  const [stepApprover, setStepApprover] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError>();

  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This request doesn't exist or isn't shared with you." : q.error.message} onRetry={q.error.status === 404 ? undefined : q.reload} /></PageFrame>;
  const d = q.data;
  if (!d) return <DetailSkeleton />;

  const owner = me?.employee.id === d.requester.id;
  const staff = me?.role !== "employee" && !owner;
  const has = (a: string) => d.actions.includes(a);
  const Icon = KIND_ICON[d.kind];
  const next = nextStepCopy(d, owner);
  const flowActions = PRIMARY_ORDER.filter(has);
  const crumbs = owner ? [{ label: "My Requests", href: "/me/requests" }, { label: d.reference }] : [{ label: "Requests & Concerns", href: "/requests/all" }, { label: d.reference }];

  async function run(action: string, body: Record<string, unknown> = {}) {
    setBusy(true);
    setError(undefined);
    try {
      const res = await post<Detail>(`/api/v1/requests/${d!.id}/actions/${action}`, body);
      q.setData(res);
      setDialog(null);
      setMessage("");
      toast(`${DONE_LABEL[action] ?? SPECS[action]?.label ?? "Updated"} · ${res.reference}`);
      invalidate();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  function trigger(action: string) {
    if (action === "submit") return run("submit");
    if (action === "start") return run("start");
    setError(undefined);
    setMessage("");
    setDialog(action);
  }

  async function removeDraft() {
    if (!confirm("Delete this draft? This cannot be undone.")) return;
    await api(`/api/v1/requests/${d!.id}`, { method: "DELETE" });
    invalidate();
    toast("Draft deleted");
    router.push("/me/requests");
  }

  const spec = dialog ? SPECS[dialog] : undefined;

  return (
    <PageFrame>
      <Breadcrumbs crumbs={crumbs} />
      <header className="flex items-start gap-4 sm:gap-5">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Icon className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {d.reference} · {d.kind_label}
            {d.category ? ` · ${d.category}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-[1.15] tracking-[-0.02em] text-balance sm:text-[30px]">{d.subject || "Untitled draft"}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            <StatusBadge status={d.status} />
            <PriorityLabel priority={d.priority} />
            <SlaLabel sla={d.sla} />
            {d.escalation_level > 0 && <span className="text-[12.5px] font-medium text-danger">Escalated · level {d.escalation_level}</span>}
          </div>
        </div>
      </header>

      {/* What happens next, and what you can do about it */}
      <section className={cn("mt-6 rounded-[var(--radius-panel)] border bg-sheet p-4 sm:p-5", flowActions.length || has("edit") ? "border-ink" : "border-line")}>
        <p className="text-[15px] font-bold">{next.title}</p>
        {next.body && <p className="mt-1 text-[14px] leading-relaxed text-ink-2">{next.body}</p>}
        {(flowActions.length > 0 || has("edit") || has("delete") || has("cancel")) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {has("edit") && (
              <Link href={`/r/${d.id}/edit`} className={buttonClass(d.status === "returned" ? "primary" : "secondary")}>
                <Pencil className="size-4" strokeWidth={1.75} aria-hidden="true" />
                {d.status === "returned" ? "Edit and resubmit" : "Edit"}
              </Link>
            )}
            {flowActions.map((a) => (
              <Button key={a} variant={SPECS[a].variant} icon={SPECS[a].icon} onClick={() => trigger(a)} busy={busy && dialog === null}>
                {SPECS[a].label}
              </Button>
            ))}
            {has("delete") && (
              <Button variant="ghost" icon={Trash2} onClick={removeDraft}>
                Delete draft
              </Button>
            )}
            {has("cancel") && (
              <Button variant="danger" icon={Ban} onClick={() => trigger("cancel")} className="sm:ml-auto">
                Cancel request
              </Button>
            )}
          </div>
        )}
        {error && !dialog && (
          <p role="alert" className="mt-3 text-[13.5px] text-danger">
            {error.message}
          </p>
        )}
      </section>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          {(d.description || d.purpose) && (
            <Panel title="Details">
              <div className="space-y-4 p-4 sm:p-5">
                {d.description && <p className="whitespace-pre-line text-[15px] leading-relaxed">{d.description}</p>}
                {d.purpose && (
                  <div>
                    <p className="text-[12.5px] font-medium text-ink-3">Purpose</p>
                    <p className="mt-1 whitespace-pre-line text-[14.5px] leading-relaxed">{d.purpose}</p>
                  </div>
                )}
              </div>
            </Panel>
          )}

          {d.items.length > 0 && (
            <Panel title="Items" meta={`${d.items.length}`}>
              <ul className="divide-y divide-line">
                {d.items.map((it, i) => (
                  <li key={it.id ?? i} className="flex items-start gap-3 px-4 py-3 sm:px-5">
                    <span className="tabular mt-0.5 w-5 shrink-0 text-[12.5px] text-mute">{i + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14.5px] font-medium">{it.item_name}</span>
                      <span className="block text-[12.5px] text-ink-3">{[it.item_category, it.brand, it.model, it.description].filter(Boolean).join(" · ") || "—"}</span>
                    </span>
                    <span className="tabular shrink-0 text-[14px] font-medium">
                      {it.quantity} {it.unit}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {d.steps.length > 0 && (
            <Panel
              title="Approval route"
              meta={`${d.steps_done} of ${d.steps_total}`}
              actions={
                has("reassign_step") ? (
                  <Button size="sm" variant="ghost" icon={UserCog} onClick={() => (setStepApprover(null), setDialog("reassign_step"))}>
                    Change approver
                  </Button>
                ) : undefined
              }
            >
              <div className="p-4 sm:p-5">
                <ApprovalRoute steps={d.steps} requester={d.requester.name} submittedAt={d.submitted_at} done={["approved", "in_progress", "awaiting_finance", "fulfilled", "closed"].includes(d.status)} />
              </div>
            </Panel>
          )}

          <Timeline d={d} canComment={has("comment")} staffView={Boolean(staff)} onChange={q.setData} />
        </div>

        <aside className="flex flex-col gap-5">
          <Panel title="Information">
            <dl className="divide-y divide-line text-[13.5px]">
              {!owner && <Row k="From" v={d.requester.name} sub={d.department?.name ?? undefined} />}
              <Row
                k="Priority"
                v={PRIORITY_LABEL[d.priority]}
                sub={d.priority !== d.requested_priority ? `Requested ${PRIORITY_LABEL[d.requested_priority]}` : undefined}
                action={has("set_priority") ? () => (setPriority(d.priority), setDialog("set_priority")) : undefined}
              />
              {d.needed_by && <Row k="Needed by" v={fmtDate(d.needed_by)} />}
              {d.location && <Row k="Where" v={d.location} />}
              <Row
                k="Owner"
                v={d.assigned_to?.name ?? "Unassigned"}
                action={has("assign") ? () => (setAssignee(d.assigned_to?.id ?? null), setDialog("assign")) : undefined}
                actionIcon={d.assigned_to ? UserCog : UserPlus}
              />
              {d.resolution_due_at && <Row k="Resolve by" v={fmtDateTime(d.resolution_due_at)} danger={d.sla === "overdue"} />}
            </dl>
            <details className="group border-t border-line">
              <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 px-4 text-[13px] font-medium text-ink-2 hover:text-ink sm:px-5 [&::-webkit-details-marker]:hidden">
                <ChevronDown className="size-4 transition-transform duration-200 group-open:rotate-180" strokeWidth={1.75} aria-hidden="true" />
                More details
              </summary>
              <dl className="divide-y divide-line border-t border-line text-[13.5px]">
                <Row k="Requester" v={d.requester.name} sub={d.requester.employee_no} />
                <Row k="Company" v={d.company.name} />
                <Row k="Department" v={d.department?.name ?? "—"} />
                {d.department_head && <Row k="Department head" v={d.department_head.name} />}
                {d.related_asset && <Row k="Related asset" v={d.related_asset} />}
                {d.delivery_location && <Row k="Deliver to" v={d.delivery_location} />}
                {d.fulfillment_status && <Row k="Fulfillment" v={d.fulfillment_status} />}
                <Row k="Created" v={fmtDateTime(d.created_at)} />
              </dl>
            </details>
          </Panel>
          <Attachments d={d} onChange={q.reload} />
          {d.status !== "draft" && <DocumentsPanel relatedType="request" relatedId={d.id} />}
        </aside>
      </div>

      {/* Generic message dialog */}
      <Dialog
        open={Boolean(spec?.dialog)}
        onClose={() => setDialog(null)}
        title={spec?.dialog?.title ?? ""}
        description={spec?.dialog?.description}
        footer={
          <>
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button
              variant={spec?.variant === "danger" ? "danger" : "primary"}
              busy={busy}
              disabled={Boolean(spec?.dialog?.required && !message.trim())}
              onClick={() => dialog && run(dialog, { message })}
            >
              {spec?.dialog?.confirm}
            </Button>
          </>
        }
      >
        {spec?.dialog?.field && (
          <Field label={spec.dialog.field} required={spec.dialog.required} htmlFor="action-message" error={error?.fields.message ?? error?.fields.comment ?? (error && !Object.keys(error.fields).length ? error.message : undefined)}>
            <Textarea id="action-message" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
          </Field>
        )}
      </Dialog>

      <Dialog
        open={dialog === "assign"}
        onClose={() => setDialog(null)}
        title="Assign an owner"
        description="Only Admin and Assistant users with access to this company can own requests."
        footer={
          <>
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button variant="primary" busy={busy} disabled={!assignee} onClick={() => run("assign", { assignee_id: assignee, message })}>
              Assign
            </Button>
          </>
        }
      >
        <Field label="Owner" htmlFor="assignee" error={error?.fields.assignee_id ? error.message : undefined}>
          <PeoplePicker id="assignee" value={assignee} onChange={setAssignee} role={["admin", "assistant"]} />
        </Field>
      </Dialog>

      <Dialog
        open={dialog === "set_priority"}
        onClose={() => setDialog(null)}
        title="Set effective priority"
        description="Changes the SLA deadlines from the time of submission."
        footer={
          <>
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button variant="primary" busy={busy} onClick={() => run("set_priority", { priority, message })}>
              Save priority
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Segmented<Priority>
            label="Priority"
            value={priority}
            onChange={setPriority}
            options={(["low", "normal", "high", "critical"] as Priority[]).map((p) => ({ value: p, label: PRIORITY_LABEL[p], icon: p === "high" || p === "critical" ? Flag : undefined }))}
          />
          <Field label="Reason (optional)" htmlFor="prio-reason">
            <Textarea id="prio-reason" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={dialog === "reassign_step"}
        onClose={() => setDialog(null)}
        title={`Change approver · ${d.current_step?.name ?? ""}`}
        description="Only people with an approval grant appear. The requester cannot approve their own request."
        footer={
          <>
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button variant="primary" busy={busy} disabled={!stepApprover} onClick={() => run("reassign_step", { step_id: d.current_step?.id, approver_id: stepApprover, message })}>
              Change approver
            </Button>
          </>
        }
      >
        <Field label="Approver" htmlFor="step-approver" error={error ? error.message : undefined}>
          <PeoplePicker id="step-approver" value={stepApprover} onChange={setStepApprover} approvers exclude={[d.requester.id]} />
        </Field>
      </Dialog>
    </PageFrame>
  );
}

function Row({ k, v, sub, action, actionIcon: AIcon = Pencil, danger }: { k: string; v: string; sub?: string; action?: () => void; actionIcon?: typeof Pencil; danger?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 py-2.5 sm:px-5">
      <dt className="pt-0.5 text-ink-3">{k}</dt>
      <dd className="flex min-w-0 items-start gap-1.5 text-right">
        <span className="min-w-0">
          <span className={cn("block font-medium", danger && "text-danger")}>{v}</span>
          {sub && <span className="tabular block text-[12px] text-ink-3">{sub}</span>}
        </span>
        {action && (
          <button type="button" onClick={action} aria-label={`Change ${k.toLowerCase()}`} className="-my-1 -mr-1.5 flex size-8 shrink-0 items-center justify-center rounded-[6px] text-ink-3 hover:bg-hover hover:text-ink">
            <AIcon className="size-4" strokeWidth={1.75} />
          </button>
        )}
      </dd>
    </div>
  );
}

const EVENT_ICON: Record<string, typeof Check> = {
  created: Pencil,
  edited: Pencil,
  submitted: Send,
  resubmitted: Send,
  step_approved: Check,
  stage_advanced: Check,
  approved: CircleCheck,
  returned: Undo2,
  rejected: X,
  withdrawn: Ban,
  cancelled: Ban,
  assigned: UserPlus,
  priority: Flag,
  processing: Play,
  awaiting_finance: Landmark,
  finance_confirmed: Landmark,
  fulfilled: PackageCheck,
  confirmed: CircleCheck,
  closed: Lock,
  reopened: RotateCcw,
  comment: MessageSquare,
  attachment: Paperclip,
  escalated: Flag,
  approver_changed: UserCog,
};

const EVENT_LABEL: Record<string, string> = {
  created: "Draft created",
  edited: "Edited",
  submitted: "Submitted",
  resubmitted: "Resubmitted",
  step_approved: "Approved",
  stage_advanced: "Moved to next stage",
  approved: "Fully approved",
  returned: "Returned for changes",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  cancelled: "Cancelled",
  assigned: "Owner set",
  priority: "Priority changed",
  processing: "Processing started",
  awaiting_finance: "Handed to Finance",
  finance_confirmed: "Finance confirmed",
  fulfilled: "Fulfilled",
  confirmed: "Confirmed by requester",
  closed: "Closed",
  reopened: "Reopened",
  comment: "Comment",
  attachment: "Attachment",
  escalated: "Escalated",
  approver_changed: "Approver changed",
};

function Timeline({ d, canComment, staffView, onChange }: { d: Detail; canComment: boolean; staffView: boolean; onChange: (d: Detail) => void }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [writing, setWriting] = useState(false);
  const [all, setAll] = useState(false);
  // stage_advanced duplicates step_approved; hide it to keep the trail readable
  const allEvents = [...d.timeline].filter((e) => e.type !== "stage_advanced").reverse();
  const events = all ? allEvents : allEvents.slice(0, 5);

  async function send() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      onChange(await post<Detail>(`/api/v1/requests/${d.id}/comments`, { message: text, internal }));
      setText("");
      setWriting(false);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Activity"
      actions={
        canComment && !writing ? (
          <Button size="sm" variant="ghost" icon={MessageSquare} onClick={() => setWriting(true)}>
            Comment
          </Button>
        ) : undefined
      }
    >
      {canComment && writing && (
        <div className="border-b border-line p-4 sm:p-5">
          <label htmlFor="comment" className="sr-only">
            Add a comment
          </label>
          <Textarea id="comment" autoFocus rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment or answer a question" />
          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
            {staffView ? (
              <div className="w-[230px]">
                <Switch checked={internal} onChange={setInternal} label="Internal note" hint="Hidden from the requester" />
              </div>
            ) : (
              <span />
            )}
            <Button size="sm" variant="primary" icon={MessageSquare} busy={busy} disabled={!text.trim()} onClick={send}>
              Post
            </Button>
          </div>
        </div>
      )}
      <ol className="px-4 py-4 sm:px-5">
        {events.map((e, i) => {
          const I = EVENT_ICON[e.type] ?? MessageSquare;
          return (
            <li key={e.id} className="relative flex gap-3 pb-4 last:pb-0">
              {i < events.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-line" aria-hidden="true" />}
              <span className={cn("relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full ring-1", e.internal ? "bg-canvas text-ink-3 ring-line" : "bg-sheet text-ink-2 ring-edge")} aria-hidden="true">
                <I className="size-3.5" strokeWidth={2} />
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <p className="text-[13.5px] leading-snug">
                  <span className="font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>
                  <span className="text-ink-3">
                    {" · "}
                    {e.actor?.name ?? "System"} · <time dateTime={e.at} title={fmtDateTime(e.at)}>{fmtRelative(e.at)}</time>
                  </span>
                  {e.internal && <span className="ml-2 rounded-[4px] px-1.5 py-px text-[11px] font-medium text-ink-3 ring-1 ring-line">Internal</span>}
                </p>
                {e.message && e.type !== "created" && <p className="mt-1 whitespace-pre-line text-[14px] leading-relaxed text-ink-2">{e.message}</p>}
              </div>
            </li>
          );
        })}
      </ol>
      {allEvents.length > 5 && (
        <div className="border-t border-line px-4 py-2 sm:px-5">
          <Button size="sm" variant="ghost" icon={ChevronDown} aria-expanded={all} onClick={() => setAll((v) => !v)}>
            {all ? "Show less" : `Show all ${allEvents.length}`}
          </Button>
        </div>
      )}
    </Panel>
  );
}

function Attachments({ d, onChange }: { d: Detail; onChange: () => void }) {
  const toast = useToast();
  const [uploading, setUploading] = useState(false);
  const can = d.actions.includes("attach");

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.set("owner_type", "request");
      fd.set("owner_id", String(d.id));
      fd.set("file", f);
      try {
        await api("/api/v1/attachments", { method: "POST", body: fd });
      } catch (e) {
        toast(`${f.name}: ${(e as ApiError).message}`, "error");
      }
    }
    setUploading(false);
    onChange();
  }

  if (!d.attachments.length && !can) return null;
  return (
    <Panel title="Attachments" meta={`${d.attachments.length}`}>
      {d.attachments.length > 0 && (
        <ul className="divide-y divide-line">
          {d.attachments.map((a) => (
            <li key={a.id}>
              <a href={a.url} className="flex items-center gap-3 px-4 py-2.5 transition-colors duration-150 hover:bg-canvas sm:px-5">
                <Paperclip className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-medium">{a.filename}</span>
                  <span className="block text-[12px] text-ink-3">
                    {fmtSize(a.size)} · {a.uploaded_by.name}
                  </span>
                </span>
                <Download className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-label="Download" />
              </a>
            </li>
          ))}
        </ul>
      )}
      {can && (
        <div className={cn("p-3 sm:px-5", d.attachments.length > 0 && "border-t border-line")}>
          <label className={cn(buttonClass("ghost", "sm"), "cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60")}>
            {uploading ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Paperclip className="size-4" strokeWidth={1.75} aria-hidden="true" />}
            {uploading ? "Uploading…" : "Attach a file"}
            <input type="file" multiple className="sr-only" accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.docx,.xlsx,.csv,.txt" onChange={(e) => (upload(e.target.files), (e.target.value = ""))} />
          </label>
        </div>
      )}
    </Panel>
  );
}

function DetailSkeleton() {
  return (
    <PageFrame>
      <div aria-hidden="true" className="animate-pulse">
        <div className="h-4 w-40 rounded-full bg-line" />
        <div className="mt-6 h-8 w-2/3 rounded-full bg-line" />
        <div className="mt-4 h-7 w-56 rounded-full bg-line/70" />
        <div className="mt-6 h-28 rounded-[var(--radius-panel)] bg-line/50" />
        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]">
          <div className="h-64 rounded-[var(--radius-panel)] bg-line/40" />
          <div className="h-64 rounded-[var(--radius-panel)] bg-line/40" />
        </div>
      </div>
      <span className="sr-only">Loading request</span>
    </PageFrame>
  );
}

