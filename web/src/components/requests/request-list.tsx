"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight, Inbox, Search, SlidersHorizontal, UserRound } from "lucide-react";
import { fmtDate, fmtRelative, qs, useApi, type Kind, type Page, type RequestSummary } from "@/lib/api";
import { Button, Chip, Input, Select } from "@/components/ui/controls";
import { EmptyState, ErrorState, Pager, Panel, SkeletonRows } from "@/components/ui/feedback";
import { KIND_ICON, PriorityLabel, SlaLabel, StatusBadge } from "@/components/ui/status";
import { cn } from "@/lib/cn";

type Group = "open" | "approval" | "processing" | "attention" | "done";

export type ListPreset = {
  scope: "mine" | "all";
  kind?: Kind[];
  group?: Group;
  priority?: string[];
  sla?: "overdue" | "due_soon";
  sort?: "newest" | "oldest" | "due" | "priority" | "updated";
  assigned?: "me" | "unassigned";
};

const TYPES: { value: Kind; label: string }[] = [
  { value: "concern", label: "Concerns" },
  { value: "repair", label: "Repairs & maintenance" },
  { value: "supplies", label: "Supplies" },
  { value: "asset", label: "Equipment & assets" },
  { value: "local_purchase", label: "Local purchases" },
  { value: "other", label: "Other" },
];

const GROUPS_MINE: { value: Group | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "attention", label: "Needs you" },
  { value: "approval", label: "In approval" },
  { value: "processing", label: "Being worked on" },
  { value: "done", label: "Done" },
];

const GROUPS_OPS: { value: Group | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "approval", label: "In approval" },
  { value: "processing", label: "Processing" },
  { value: "open", label: "Open" },
  { value: "done", label: "Done" },
];

/** A searchable, filterable request list. Rows become cards on phones. */
export function RequestList({
  preset,
  title,
  emptyTitle,
  emptyBody,
  emptyAction,
  filters = true,
  pageSize = 20,
}: {
  preset: ListPreset;
  title?: string;
  emptyTitle: string;
  emptyBody?: string;
  emptyAction?: React.ReactNode;
  filters?: boolean;
  pageSize?: number;
}) {
  const [group, setGroup] = useState<Group | undefined>(preset.group);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState(preset.sort ?? "newest");
  const [sla, setSla] = useState(preset.sla);
  const [assigned, setAssigned] = useState(preset.assigned);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState<Kind | undefined>();
  const [showFilters, setShowFilters] = useState(false);
  const activeFilters = [kind, sla ?? assigned, sort !== (preset.sort ?? "newest") ? sort : undefined].filter(Boolean).length;

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const path = `/api/v1/requests${qs({
    scope: preset.scope,
    kind: preset.kind ?? (kind ? [kind] : undefined),
    priority: preset.priority,
    group,
    sla,
    assigned,
    q: debounced.trim(),
    sort,
    page,
    page_size: pageSize,
  })}`;
  const list = useApi<Page<RequestSummary>>(path);
  // Only the person's own search or filters count; a page's preset view is not "filtered".
  const narrowed = Boolean(q || group !== preset.group || activeFilters);
  const staff = preset.scope === "all";
  const groups = staff ? GROUPS_OPS : GROUPS_MINE;

  return (
    <Panel title={title} meta={list.data ? `${list.data.total}` : undefined}>
      {filters && (
        <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
          <div className="flex gap-2">
            <label className="relative flex-1">
              <span className="sr-only">Search requests</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
              <Input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Search"
                className="pl-9"
                type="search"
              />
            </label>
            <Button
              variant={showFilters || activeFilters ? "primary" : "secondary"}
              icon={SlidersHorizontal}
              aria-expanded={showFilters}
              onClick={() => setShowFilters((v) => !v)}
              className="px-3"
            >
              <span className="hidden sm:inline">Filters</span>
              {activeFilters > 0 && <span className="tabular text-[12px] opacity-80">{activeFilters}</span>}
            </Button>
          </div>
          {showFilters && (
            <div className="grid gap-2 sm:grid-cols-3">
              {staff && !preset.kind && (
                <Select aria-label="Type" value={kind ?? ""} onChange={(e) => (setKind((e.target.value || undefined) as Kind | undefined), setPage(1))}>
                  <option value="">All types</option>
                  {TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </Select>
              )}
              {staff && (
                <Select
                  aria-label="Owner or deadline"
                  value={sla ?? assigned ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setSla(v === "overdue" || v === "due_soon" ? v : undefined);
                    setAssigned(v === "me" || v === "unassigned" ? v : undefined);
                    setPage(1);
                  }}
                >
                  <option value="">Any owner or deadline</option>
                  <option value="overdue">Overdue</option>
                  <option value="due_soon">Due in 24 hours</option>
                  <option value="me">Assigned to me</option>
                  <option value="unassigned">No owner yet</option>
                </Select>
              )}
              <Select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
                <option value="newest">Newest first</option>
                <option value="updated">Recently updated</option>
                <option value="priority">Most urgent first</option>
                <option value="due">Due soonest</option>
                <option value="oldest">Oldest first</option>
              </Select>
            </div>
          )}
          <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 pb-0.5 sm:mx-0 sm:px-0" role="group" aria-label="Status">
            {groups.map((g) => (
              <Chip
                key={g.label}
                on={group === g.value}
                onClick={() => {
                  setGroup(g.value);
                  setPage(1);
                }}
              >
                {g.label}
              </Chip>
            ))}
          </div>
        </div>
      )}
      {list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : !list.data ? (
        <SkeletonRows />
      ) : list.data.items.length === 0 ? (
        <EmptyState icon={Inbox} title={narrowed ? "No matching records" : emptyTitle} body={narrowed ? "Try another search, status or filter." : emptyBody} action={narrowed ? undefined : emptyAction} compact />
      ) : (
        <>
          <ul className={cn("divide-y divide-line transition-opacity duration-150", list.loading && "opacity-60")}>
            {list.data.items.map((r) => (
              <RequestRow key={r.id} r={r} staff={staff} />
            ))}
          </ul>
          <Pager page={page} pageSize={pageSize} total={list.data.total} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

export function RequestRow({ r, staff, extra }: { r: RequestSummary; staff?: boolean; extra?: React.ReactNode }) {
  const Icon = KIND_ICON[r.kind];
  const step = r.current_step;
  return (
    <li>
      <Link href={`/r/${r.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line bg-sheet text-ink sm:mt-0" aria-hidden="true">
          <Icon className="size-5" strokeWidth={1.6} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[15px] font-bold leading-snug">{r.subject || "Untitled draft"}</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-ink-3">
            <span className="tabular">{r.reference}</span>
            <span aria-hidden="true">·</span>
            <span>{r.kind_label}</span>
            {staff && (
              <>
                <span aria-hidden="true">·</span>
                <span className="inline-flex items-center gap-1">
                  <UserRound className="size-3" strokeWidth={2} aria-hidden="true" />
                  {r.requester.name}
                </span>
              </>
            )}

            {staff && r.status !== "draft" && !step && (
              <>
                <span aria-hidden="true">·</span>
                <span>{r.assigned_to ? `Owner ${r.assigned_to.name}` : "Unassigned"}</span>
              </>
            )}
          </span>
          {step && (
            <span className="mt-0.5 block text-[12.5px] text-ink-2">
              With {step.approver?.name ?? <span className="text-danger">no approver</span>} · {step.name}
            </span>
          )}
          <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:hidden">
            <StatusBadge status={r.status} />
            <PriorityLabel priority={r.priority} />
            <SlaLabel sla={r.sla} />
          </span>
          {extra}
        </span>
        <span className="hidden shrink-0 flex-col items-end gap-1.5 sm:flex">
          <StatusBadge status={r.status} />
          <span className="flex items-center gap-3">
            <SlaLabel sla={r.sla} />
            <PriorityLabel priority={r.priority} />
          </span>
        </span>
        <span className="hidden w-[92px] shrink-0 text-right text-[12.5px] text-ink-3 md:block" title={fmtDate(r.updated_at)}>
          {fmtRelative(r.updated_at)}
        </span>
        <ChevronRight className="mt-3 size-4 shrink-0 text-mute transition-[color,transform] duration-200 group-hover:translate-x-0.5 group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}
