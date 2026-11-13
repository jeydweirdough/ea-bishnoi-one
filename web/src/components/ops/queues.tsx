"use client";

import Link from "next/link";
import {
  Boxes,
  Building2,
  CalendarClock,
  CarFront,
  ChevronRight,
  FileSignature,
  Landmark,
  Package,
  Plane,
  Wrench,
  type LucideIcon,
  CircleCheck,
  Flag,
  Gavel,
  Hourglass,
  ListTodo,
  TriangleAlert,
  } from "lucide-react";
import { qs, useApi, type Kind, type Page, type RequestSummary, type Task } from "@/lib/api";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { CountStrip, EmptyState, Panel, SkeletonRows } from "@/components/ui/feedback";
import { PriorityLabel } from "@/components/ui/status";
import { RequestList, RequestRow, type ListPreset } from "@/components/requests/request-list";
import { RouteProgress } from "@/components/requests/approval-route";
import { useShell } from "@/components/shell/shell-context";
import { DataTools } from "@/components/io/data-tools";
import { crumbsFor } from "@/lib/nav";
import { cn } from "@/lib/cn";

export type ModuleMeta = { href: string; label: string; summary: string };

function Header({ meta, children, actions }: { meta: ModuleMeta; children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <>
      <Breadcrumbs crumbs={crumbsFor(meta.href)} />
      <PageHeader title={meta.label} summary={meta.summary} icon={iconForHref(meta.href)} actions={actions}>
        {children}
      </PageHeader>
    </>
  );
}


const QUEUE_KINDS: Record<string, Kind[] | undefined> = {
  all: undefined,
  "asset-requests": ["asset"],
  "local-purchase": ["local_purchase"],
  supplies: ["supplies"],
  "repairs-maintenance": ["repair"],
  "department-concerns": ["concern"],
  other: ["other"],
};

/** Requests & Concerns queues — the same list, narrowed by request type. */
export function RequestQueue({ meta, slug }: { meta: ModuleMeta; slug: string }) {
  const { me } = useShell();
  const assistant = me?.role === "assistant";
  return (
    <PageFrame>
      <Header
        actions={slug === "all" ? <DataTools dataset="requests" /> : undefined}
        meta={slug === "all" ? { ...meta, label: "Requests", summary: assistant ? "Requests assigned to you." : "Every request across your companies." } : meta}>
      </Header>
      <div className="mt-8 lg:mt-10">
        <RequestList
          preset={{ scope: "all", kind: QUEUE_KINDS[slug] }}
          emptyTitle={assistant ? "No requests assigned to you" : "No requests here yet"}
          emptyBody={assistant ? "Requests an Admin assigns to you appear here." : "Submitted requests of this type appear here as employees send them."}
        />
      </div>
    </PageFrame>
  );
}

/** Pending approvals (dashboard) and Approval Tracking (requests) — who holds each request now. */
export function ApprovalTracking({ meta, preset }: { meta: ModuleMeta; preset?: Partial<ListPreset> }) {
  const path = `/api/v1/requests${qs({ scope: "all", group: "approval", sort: preset?.sort ?? "oldest", page_size: 50 })}`;
  const q = useApi<Page<RequestSummary>>(path);
  const byApprover = new Map<string, RequestSummary[]>();
  for (const r of q.data?.items ?? []) {
    const key = r.status === "returned" ? "Returned to requester" : (r.current_step?.approver?.name ?? "No approver assigned");
    byApprover.set(key, [...(byApprover.get(key) ?? []), r]);
  }
  return (
    <PageFrame>
      <Header meta={meta} />
      <div className="mt-8 grid gap-5 lg:mt-10 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-6">
        <Panel title="In approval" meta={q.data ? `${q.data.total}` : undefined}>
          {!q.data ? (
            <SkeletonRows />
          ) : q.data.items.length === 0 ? (
            <EmptyState icon={CircleCheck} title="No requests pending approval" body="Submitted requests show here until every stage has decided." compact />
          ) : (
            <ul className="divide-y divide-line">
              {q.data.items.map((r) => (
                <RequestRow key={r.id} r={r} staff extra={<RouteProgress r={r} />} />
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Waiting on">
          {byApprover.size === 0 ? (
            <p className="p-4 text-[13.5px] text-ink-3 sm:px-5">No one.</p>
          ) : (
            <ul className="divide-y divide-line">
              {[...byApprover.entries()]
                .sort((a, b) => b[1].length - a[1].length)
                .map(([name, rs]) => (
                  <li key={name} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13.5px] sm:px-5">
                    <span className={cn("min-w-0 truncate", name === "No approver assigned" && "text-danger")}>{name}</span>
                    <span className="tabular font-medium">{rs.length}</span>
                  </li>
                ))}
            </ul>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

export function PriorityConcerns({ meta }: { meta: ModuleMeta }) {
  return (
    <PageFrame>
      <Header meta={meta} />
      <div className="mt-8 flex flex-col gap-5 lg:mt-10">
        <RequestList preset={{ scope: "all", group: "open", sla: "overdue", sort: "priority" }} title="Overdue" filters={false} emptyTitle="No overdue requests" pageSize={10} />
        <RequestList preset={{ scope: "all", group: "open", priority: ["critical", "high"], sort: "priority" }} title="High and critical, open" filters={false} emptyTitle="No high-priority requests are open" pageSize={20} />
      </div>
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- overview */


type Exec = {
  total_open_requests: number;
  pending_approvals: number;
  overdue_requests: number;
  priority_concerns: number;
  upcoming_renewals: number;
  active_assets: number;
  assets_under_repair: number;
  fleet_maintenance_due: number;
  expiring_government_documents: number;
  contract_renewals: number;
  travel_requests: number;
  low_stock: number;
  task_completion: { done: number; due: number; pct: number | null };
};
type AssistantDash = { assigned_requests: number; assigned_tasks: number; overdue_follow_ups: number; pending_documents: number; upcoming_renewals: number; awaiting_coordination: number };

export function OperationsOverview({ meta }: { meta: ModuleMeta }) {
  const { me } = useShell();
  const assistant = me?.role === "assistant";
  const ex = useApi<Exec>(assistant ? null : "/api/v1/dashboard/executive");
  const asd = useApi<AssistantDash>(assistant ? "/api/v1/dashboard/assistant" : null);
  const tasks = useApi<Page<Task> & { mine: { open: number; in_progress: number; done: number; overdue: number } }>("/api/v1/tasks?view=mine&status=open&status=in_progress&page_size=5");
  const e = ex.data;
  const a = asd.data;
  const watch: [LucideIcon, string, number | string | undefined, string, boolean?][] = assistant
    ? [
        [ListTodo, "Tasks assigned to me", a?.assigned_tasks, "/administration/tasks"],
        [TriangleAlert, "Overdue follow-ups", a?.overdue_follow_ups, "/requests/all", true],
        [Landmark, "Pending with Finance", a?.pending_documents, "/requests/all"],
        [CalendarClock, "My renewals (60 days)", a?.upcoming_renewals, "/compliance/registrations"],
        [Hourglass, "Approved, pending action", a?.awaiting_coordination, "/requests/all"],
      ]
    : [
        [CalendarClock, "Upcoming renewals", e?.upcoming_renewals, "/dashboard/upcoming-renewals"],
        [Building2, "Expiring government documents (60 days)", e?.expiring_government_documents, "/compliance/registrations"],
        [FileSignature, "Contracts for renewal", e?.contract_renewals, "/contracts/renewals"],
        [Wrench, "Assets under repair", e?.assets_under_repair, "/assets/repairs"],
        [CarFront, "Vehicles due for PMS (30 days)", e?.fleet_maintenance_due, "/fleet/registration-insurance"],
        [Boxes, "Low-stock items", e?.low_stock, "/assets/inventory", true],
        [Plane, "Travel bookings in progress", e?.travel_requests, "/travel/flights"],
        [Package, "Active assets", e?.active_assets, "/assets/registry"],
        [CircleCheck, "Tasks completed this month", e ? (e.task_completion.due ? `${e.task_completion.done} of ${e.task_completion.due}` : String(e.task_completion.done)) : undefined, "/administration/tasks"],
      ];
  return (
    <PageFrame>
      <Header meta={{ ...meta, label: assistant ? "My Assignments" : "Overview", summary: assistant ? "Requests and tasks assigned to you, including overdue items." : "Operational summary from live records." }} />
      <div className="mt-8 lg:mt-10">
        <CountStrip
          items={
            assistant
              ? [
                  { icon: ListTodo, label: "Assigned requests", value: a?.assigned_requests, href: "/requests/all" },
                  { icon: ListTodo, label: "Assigned tasks", value: a?.assigned_tasks, href: "/administration/tasks" },
                  { icon: TriangleAlert, label: "Overdue", value: a?.overdue_follow_ups, href: "/dashboard/priority-concerns", danger: true },
                  { icon: CalendarClock, label: "Renewals (60 days)", value: a?.upcoming_renewals, href: "/compliance/registrations" },
                ]
              : [
                  { icon: ListTodo, label: "Open requests", value: e?.total_open_requests, href: "/requests/all" },
                  { icon: Hourglass, label: "In approval", value: e?.pending_approvals, href: "/requests/approval-tracking" },
                  { icon: TriangleAlert, label: "Overdue", value: e?.overdue_requests, href: "/dashboard/priority-concerns", danger: true },
                  { icon: Flag, label: "High / urgent", value: e?.priority_concerns, href: "/dashboard/priority-concerns" },
                ]
          }
        />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Requires attention">
            <ul className="divide-y divide-line">
              {watch.map(([I, label, value, href, warn]) => (
                <li key={label}>
                  <Link href={href} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas sm:px-5">
                    <I className={cn("size-[18px] shrink-0", warn && value ? "text-danger" : "text-ink-3")} strokeWidth={1.75} aria-hidden="true" />
                    <span className="min-w-0 flex-1 text-[14px]">{label}</span>
                    <span className={cn("tabular text-[15px] font-bold", warn && value ? "text-danger" : "")}>{value ?? "–"}</span>
                    <ChevronRight className="size-4 shrink-0 text-mute" strokeWidth={1.75} aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
          <RequestList preset={{ scope: "all", group: "processing", sort: "priority" }} title="For processing" filters={false} emptyTitle="No requests for processing" emptyBody="Approved requests arrive here for fulfilment." pageSize={6} />
        </div>
        <Panel title="My tasks" meta={tasks.data ? `${tasks.data.mine.open + tasks.data.mine.in_progress} open` : undefined} actions={<Link href="/administration/tasks" className="text-[13px] font-medium text-ink-2 hover:text-ink hover:underline">All tasks</Link>}>
          {!tasks.data ? (
            <SkeletonRows rows={3} />
          ) : tasks.data.items.length === 0 ? (
            <EmptyState icon={CircleCheck} title="No open tasks" compact />
          ) : (
            <ul className="divide-y divide-line">
              {tasks.data.items.map((t) => (
                <li key={t.id}>
                  <Link href="/administration/tasks" className="flex items-center gap-3 px-4 py-3 hover:bg-canvas sm:px-5">
                    <ListTodo className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{t.title}</span>
                      <span className={cn("block text-[12.5px]", t.overdue ? "font-medium text-danger" : "text-ink-3")}>{t.due_date ? `${t.overdue ? "Overdue · " : "Due "}${t.due_date}` : "No due date"}</span>
                    </span>
                    <PriorityLabel priority={t.priority} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      {me?.navigation.approval_inbox && me.inbox_count > 0 && (
        <Link href="/inbox" className="mt-5 flex items-center gap-3 rounded-[var(--radius-panel)] border border-line bg-sheet px-4 py-3.5 text-[14px] hover:bg-canvas sm:px-5">
          <Gavel className="size-5" strokeWidth={1.6} aria-hidden="true" />
          {me.inbox_count} waiting in your Approval Inbox
        </Link>
      )}
    </PageFrame>
  );
}
