"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Bell,
  BellOff,
  CheckCheck,
  ChevronRight,
  CircleCheck,
  Clock,
  FileClock,
  Gavel,
  Hourglass,
  ListChecks,
  LoaderCircle,
  MessageSquare,
  MessageSquareWarning,
  PackageCheck,
  PackagePlus,
  Plus,
  TriangleAlert,
  UserPlus,
  Landmark,
  type LucideIcon,
} from "lucide-react";
import { fmtRelative, post, invalidate, qs, useApi, type Notice, type Page, type RequestSummary } from "@/lib/api";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { Button, Chip, buttonClass } from "@/components/ui/controls";
import { CountStrip, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RequestForm } from "@/components/requests/request-form";
import { RequestList, RequestRow } from "@/components/requests/request-list";
import { RouteProgress } from "@/components/requests/approval-route";
import { useShell } from "@/components/shell/shell-context";
import { SELF_SERVICE, crumbsFor, selfHref } from "@/lib/nav";
import { cn } from "@/lib/cn";

/** Plain-language headings; the catalogue wording in nav.ts stays for search and breadcrumbs. */
const COPY: Record<string, { title: string; summary: string }> = {
  "raise-concern": { title: "Report a problem", summary: "Tell us what's wrong. We'll route it for approval and keep you posted." },
  "request-supplies": { title: "Request items", summary: "Add what you need. We'll route it for approval and let you know when it's ready." },
  requests: { title: "My requests", summary: "Everything you've sent, and where each one is now." },
  "approvals-status": { title: "In approval", summary: "Who has each request now." },
  notifications: { title: "Notifications", summary: "Decisions, questions and updates on your requests." },
};

function Header({ slug, children, back }: { slug: string; children?: React.ReactNode; back?: { label: string; href: string } }) {
  const item = SELF_SERVICE.find((s) => s.slug === slug)!;
  const copy = COPY[slug] ?? { title: item.label, summary: item.summary };
  return (
    <>
      <Breadcrumbs crumbs={back ? [back, { label: copy.title }] : crumbsFor(selfHref(item))} />
      <PageHeader title={copy.title} summary={copy.summary} icon={iconForHref(selfHref(item))}>
        {children}
      </PageHeader>
    </>
  );
}

/* ---------------------------------------------------------------- dashboard */

type Stats = { total: number; drafts: number; in_approval: number; in_progress: number; completed: number; open: number; needs_you: number };

export function MyDashboard() {
  const { me } = useShell();
  const stats = useApi<Stats>("/api/v1/requests/stats?scope=mine");
  const attention = useApi<Page<RequestSummary>>(`/api/v1/requests${qs({ scope: "mine", group: "attention", page_size: 5 })}`);
  const recent = useApi<Page<RequestSummary>>(`/api/v1/requests${qs({ scope: "mine", sort: "updated", page_size: 4 })}`);
  const notes = useApi<Page<Notice>>("/api/v1/notifications?page_size=4");
  const assets = useApi<{ id: number; name: string; reference: string; awaiting_acknowledgement: boolean }[]>("/api/v1/me/assets");
  const toAck = assets.data?.filter((a) => a.awaiting_acknowledgement) ?? [];
  const s = stats.data;
  const first = me?.employee.name.split(" ")[0];

  return (
    <PageFrame>
      <PageHeader display title={first ? `Welcome, ${first}` : "Welcome"} summary="Status of your requests and the actions waiting on you." icon={iconForHref("/me")}
        actions={
          <>
          <Link href="/me/raise-concern" className={buttonClass("primary")}>
            <MessageSquareWarning className="size-4" strokeWidth={1.75} aria-hidden="true" />
            Report a problem
          </Link>
          <Link href="/me/request-supplies" className={buttonClass("secondary")}>
            <PackagePlus className="size-4" strokeWidth={1.75} aria-hidden="true" />
            Request items
          </Link>
          </>
        }
      />

      <div className="mt-8 lg:mt-10">
        <CountStrip
          items={[
            { icon: ListChecks, label: "Open", value: s?.open, href: "/me/requests" },
            { icon: Hourglass, label: "In approval", value: s?.in_approval, href: "/me/approvals-status" },
            { icon: LoaderCircle, label: "Being worked on", value: s?.in_progress, href: "/me/requests" },
            { icon: CircleCheck, label: "Done", value: s?.completed, href: "/me/requests" },
          ]}
        />
      </div>

      {toAck.length > 0 && (
        <Link href="/me/assets" className="group mt-5 flex items-center gap-4 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 transition-colors duration-150 hover:bg-canvas sm:px-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-ink text-white" aria-hidden="true">
            <PackageCheck className="size-5" strokeWidth={1.6} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-bold">
              Acknowledge receipt: {toAck.length === 1 ? toAck[0].name : `${toAck.length} items`}
            </span>
            <span className="block text-[13px] text-ink-3">Issued to you by Executive Admin</span>
          </span>
          <ChevronRight className="size-4 text-mute transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-ink" strokeWidth={1.75} aria-hidden="true" />
        </Link>
      )}

      {me?.navigation.approval_inbox && me.inbox_count > 0 && (
        <Link href="/inbox" className="group mt-5 flex items-center gap-4 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 transition-colors duration-150 hover:bg-canvas sm:px-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-ink text-white" aria-hidden="true">
            <Gavel className="size-5" strokeWidth={1.6} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-bold">
              {me.inbox_count} {me.inbox_count === 1 ? "request is" : "requests are"} waiting for your decision
            </span>
            <span className="block text-[13px] text-ink-3">Open your Approval Inbox</span>
          </span>
          <ChevronRight className="size-4 text-mute transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-ink" strokeWidth={1.75} aria-hidden="true" />
        </Link>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          {attention.data && attention.data.items.length > 0 && (
            <Panel title="Needs you" meta={`${attention.data.total}`}>
              <ul className="divide-y divide-line">
                {attention.data.items.map((r) => (
                  <RequestRow key={r.id} r={r} />
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Recent requests" actions={<Link href="/me/requests" className="text-[13px] font-medium text-ink-2 hover:text-ink hover:underline">See all</Link>}>
            {recent.error ? (
              <ErrorState message={recent.error.message} onRetry={recent.reload} />
            ) : !recent.data ? (
              <SkeletonRows rows={3} />
            ) : recent.data.items.length === 0 ? (
              <EmptyState icon={ListChecks} title="No requests yet" body="Raise a concern or request supplies — you can save a draft and finish later." compact />
            ) : (
              <ul className="divide-y divide-line">
                {recent.data.items.map((r) => (
                  <RequestRow key={r.id} r={r} />
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <Panel title="Latest updates" actions={<Link href="/me/notifications" className="text-[13px] font-medium text-ink-2 hover:text-ink hover:underline">All</Link>}>
          {!notes.data ? (
            <SkeletonRows rows={3} />
          ) : notes.data.items.length === 0 ? (
            <EmptyState icon={BellOff} title="No new notifications" body="Decisions, comments and status changes show up here." compact />
          ) : (
            <NoticeList items={notes.data.items} compact />
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- forms */

export function RaiseConcernPage() {
  return (
    <PageFrame>
      <Header slug="raise-concern" back={{ label: "New request", href: "/me/new" }} />
      <RequestForm mode="concern" />
    </PageFrame>
  );
}

export function RequestSuppliesPage() {
  return (
    <PageFrame>
      <Header slug="request-supplies" back={{ label: "New request", href: "/me/new" }} />
      <RequestForm mode="supplies" />
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- lists */

export function MyRequestsPage() {
  return (
    <PageFrame>
      <Header slug="requests" />
      <div className="mt-8 lg:mt-10">
        <RequestList
          preset={{ scope: "mine" }}
          emptyTitle="No requests yet"
          emptyBody="Concerns and supply requests you create appear here, drafts included."
          emptyAction={
            <Link href="/me/new" className={buttonClass("primary")}>
              <Plus className="size-4" strokeWidth={1.75} aria-hidden="true" />
              New request
            </Link>
          }
        />
      </div>
    </PageFrame>
  );
}

export function ApprovalsStatusPage() {
  const [page, setPage] = useState(1);
  const q = useApi<Page<RequestSummary>>(`/api/v1/requests${qs({ scope: "mine", group: "approval", sort: "oldest", page, page_size: 20 })}`);
  return (
    <PageFrame>
      <Header slug="approvals-status" />
      <div className="mt-8 lg:mt-10">
        <Panel title="Waiting for approval" meta={q.data ? `${q.data.total}` : undefined}>
          {q.error ? (
            <ErrorState message={q.error.message} onRetry={q.reload} />
          ) : !q.data ? (
            <SkeletonRows rows={3} />
          ) : q.data.items.length === 0 ? (
            <EmptyState icon={CircleCheck} title="No requests in approval" body="When you submit a request, you can follow each approval stage here." compact />
          ) : (
            <>
              <ul className="divide-y divide-line">
                {q.data.items.map((r) => (
                  <RequestRow key={r.id} r={r} extra={<RouteProgress r={r} />} />
                ))}
              </ul>
              <Pager page={page} pageSize={20} total={q.data.total} onPage={setPage} />
            </>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- notifications */

const NOTICE_ICON: Record<string, LucideIcon> = {
  new_request: PackagePlus,
  approval_required: Gavel,
  approval_decision: CheckCheck,
  task_assignment: UserPlus,
  due_date_reminder: Clock,
  overdue_notice: TriangleAlert,
  renewal_warning: FileClock,
  payment_status: Landmark,
  fulfillment_confirmation: PackageCheck,
  comment: MessageSquare,
};

function NoticeList({ items, compact }: { items: Notice[]; compact?: boolean }) {
  const router = useRouter();
  return (
    <ul className="divide-y divide-line">
      {items.map((n) => {
        const Icon = NOTICE_ICON[n.kind] ?? Bell;
        return (
          <li key={n.id}>
            <button
              type="button"
              onClick={async () => {
                if (!n.read) await post(`/api/v1/notifications/${n.id}/read`).catch(() => {});
                invalidate();
                if (n.link) router.push(n.link);
              }}
              className={cn("flex w-full items-start gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-canvas sm:px-5", compact && "py-2.5")}
            >
              <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-[8px] border", n.read ? "border-line text-ink-3" : "border-ink bg-ink text-white")} aria-hidden="true">
                <Icon className="size-4" strokeWidth={1.75} />
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn("block text-[14px] leading-snug", n.read ? "text-ink-2" : "font-bold text-ink")}>{n.title}</span>
                {n.body && !compact && <span className="mt-0.5 block text-[13px] leading-snug text-ink-3">{n.body}</span>}
                <span className="mt-0.5 block text-[12px] text-ink-3">{fmtRelative(n.created_at)}</span>
              </span>
              {!n.read && <span className="mt-2 size-2 shrink-0 rounded-full bg-accent" aria-label="Unread" />}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function NotificationsPage() {
  const toast = useToast();
  const [unread, setUnread] = useState(false);
  const [page, setPage] = useState(1);
  const q = useApi<Page<Notice>>(`/api/v1/notifications${qs({ unread, page, page_size: 30 })}`);
  return (
    <PageFrame>
      <Header slug="notifications" />
      <div className="mt-8 lg:mt-10">
        <Panel
          title="Inbox"
          meta={q.data ? `${q.data.total}` : undefined}
          actions={
            <Button
              size="sm"
              variant="ghost"
              icon={CheckCheck}
              onClick={async () => {
                const r = await post<{ updated: number }>("/api/v1/notifications/read-all");
                toast(r.updated ? `Marked ${r.updated} as read` : "Everything is already read");
                invalidate();
              }}
            >
              Mark all read
            </Button>
          }
        >
          <div className="flex gap-1.5 border-b border-line p-3 sm:px-5">
            <Chip on={!unread} onClick={() => (setUnread(false), setPage(1))}>
              All
            </Chip>
            <Chip on={unread} onClick={() => (setUnread(true), setPage(1))}>
              Unread
            </Chip>
          </div>
          {q.error ? (
            <ErrorState message={q.error.message} onRetry={q.reload} />
          ) : !q.data ? (
            <SkeletonRows />
          ) : q.data.items.length === 0 ? (
            <EmptyState icon={BellOff} title={unread ? "All caught up" : "No notifications yet"} body="Decisions, comments, assignments and reminders arrive here." compact />
          ) : (
            <>
              <NoticeList items={q.data.items} />
              <Pager page={page} pageSize={30} total={q.data.total} onPage={setPage} />
            </>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}
