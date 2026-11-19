"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronsUpDown,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Registers on desktop: a table with sortable columns and a checkbox per row. Clicking a row opens
 * the record; the checkbox selects it for the bulk-action bar. On phones the page keeps its card list.
 */

export type SortState = { key: string; dir: "asc" | "desc" };
export type Column<T> = {
  key: string;
  label: string;
  /** Sort key sent to the API; omit for columns that can't be sorted. */
  sort?: string;
  align?: "right";
  className?: string;
  render: (row: T) => React.ReactNode;
};

export function Checkbox({
  checked,
  indeterminate,
  onChange,
  label,
  className,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (on: boolean) => void;
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current)
      ref.current.indeterminate = Boolean(indeterminate) && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "size-[18px] shrink-0 cursor-pointer rounded accent-ink",
        className,
      )}
    />
  );
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  rowLabel,
  href,
  selected,
  onSelect,
  sort,
  onSort,
  caption,
  expand,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Read out for the row's checkbox, e.g. the item name. */
  rowLabel: (row: T) => string;
  href: (row: T) => string;
  selected: Set<string>;
  onSelect: (keys: string[], on: boolean) => void;
  sort: SortState;
  onSort: (s: SortState) => void;
  caption: string;
  /** Rows that stand for several records (e.g. "× 5") can open a list of them under the row. */
  expand?: {
    label: (row: T) => string | null;
    render: (row: T) => React.ReactNode;
  };
}) {
  const router = useRouter();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const keys = rows.map(rowKey);
  const all = keys.length > 0 && keys.every((k) => selected.has(k));
  const some = keys.some((k) => selected.has(k));
  return (
    <div className="hidden overflow-x-auto lg:block">
      <table className="w-full border-collapse text-[13.5px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line text-left text-[12.5px] text-ink-3">
            <th scope="col" className="w-12 py-2.5 pl-5 pr-2">
              <Checkbox
                checked={all}
                indeterminate={some}
                onChange={(on) => onSelect(keys, on)}
                label="Select all on this page"
              />
            </th>
            {columns.map((c) => {
              const active = c.sort && sort.key === c.sort;
              const Icon: LucideIcon = active
                ? sort.dir === "asc"
                  ? ArrowUp
                  : ArrowDown
                : ChevronsUpDown;
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={
                    active
                      ? sort.dir === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                  className={cn(
                    "px-3 py-2.5 font-medium",
                    c.align === "right" && "text-right",
                    c.className,
                  )}
                >
                  {c.sort ? (
                    <button
                      type="button"
                      onClick={() =>
                        onSort({
                          key: c.sort!,
                          dir:
                            active && sort.dir === "asc"
                              ? "desc"
                              : active
                                ? "asc"
                                : c.align === "right"
                                  ? "desc"
                                  : "asc",
                        })
                      }
                      className={cn(
                        "-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-ink",
                        active && "text-ink",
                      )}
                    >
                      {c.label}
                      <Icon
                        className={cn("size-3.5", !active && "opacity-40")}
                        strokeWidth={2}
                        aria-hidden="true"
                      />
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              );
            })}
            {expand && (
              <th scope="col" className="w-10 pr-4">
                <span className="sr-only">Details</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => {
            const k = rowKey(r);
            const on = selected.has(k);
            const more = expand?.label(r) ?? null;
            const isOpen = open.has(k);
            return (
              <Fragment key={k}>
                <tr
                  onClick={(e) => {
                    if (
                      (e.target as HTMLElement).closest("a,button,input,label")
                    )
                      return;
                    router.push(href(r));
                  }}
                  className={cn(
                    "cursor-pointer transition-colors duration-150 hover:bg-canvas",
                    on && "bg-canvas",
                  )}
                >
                  <td className="py-2.5 pl-5 pr-2 align-middle">
                    <Checkbox
                      checked={on}
                      onChange={(v) => onSelect([k], v)}
                      label={`Select ${rowLabel(r)}`}
                    />
                  </td>
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn(
                        "px-3 py-2.5 align-middle",
                        c.align === "right" && "text-right",
                        c.className,
                      )}
                    >
                      {c.render(r)}
                    </td>
                  ))}
                  {expand && (
                    <td className="pr-4 align-middle">
                      {more && (
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          aria-label={`${isOpen ? "Hide" : "Show"} ${more}`}
                          onClick={() =>
                            setOpen((cur) => {
                              const n = new Set(cur);
                              if (n.has(k)) n.delete(k);
                              else n.add(k);
                              return n;
                            })
                          }
                          className="flex size-8 items-center justify-center rounded-full text-ink-2 hover:bg-hover hover:text-ink"
                        >
                          <ChevronDown
                            className={cn(
                              "size-4 transition-transform duration-200",
                              isOpen && "rotate-180",
                            )}
                            strokeWidth={1.75}
                          />
                        </button>
                      )}
                    </td>
                  )}
                </tr>
                {expand && more && isOpen && (
                  <tr className="bg-canvas">
                    <td />
                    <td colSpan={columns.length + 1} className="px-3 pb-3 pt-1">
                      {expand.render(r)}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Appears while rows are selected: the count, the actions, and a way to clear. On phones the actions get their own line. */
export function BulkBar({ count, onClear, children }: { count: number; onClear: () => void; children: React.ReactNode }) {
  if (!count) return null;
  return (
    <div
      role="region"
      aria-label="Selected items"
      className="fixed inset-x-3 bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+10px)] z-40 mx-auto flex max-w-[760px] flex-wrap items-center gap-x-2 gap-y-1 rounded-[14px] bg-ink px-3 py-2 text-white shadow-lg lg:bottom-6"
    >
      <span className="tabular order-1 px-1.5 text-[14px] font-bold">{count} selected</span>
      <button type="button" onClick={onClear} aria-label="Clear the selection" className="order-2 ml-auto flex size-9 items-center justify-center rounded-full hover:bg-white/15 sm:order-3 sm:ml-0">
        <X className="size-4" strokeWidth={2} />
      </button>
      <span className="order-3 flex basis-full items-center justify-around gap-1 border-t border-white/15 pt-1 sm:order-2 sm:flex-1 sm:basis-auto sm:justify-start sm:border-0 sm:pt-0">{children}</span>
    </div>
  );
}

export function BulkAction({ icon: Icon, label, short, onClick, disabled, title }: { icon: LucideIcon; label: string; short?: string; onClick: () => void; disabled?: boolean; title?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={label}
      className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-ctl)] px-2.5 text-[13.5px] font-medium hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-45 sm:h-9"
    >
      <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
      {short ? (
        <>
          <span className="sm:hidden">{short}</span>
          <span className="hidden sm:inline">{label}</span>
        </>
      ) : (
        label
      )}
    </button>
  );
}

/** Selection kept by row key, with the rows themselves for the bulk actions. */
export function toggleKeys<T>(
  prev: Map<string, T>,
  rows: T[],
  rowKey: (r: T) => string,
  keys: string[],
  on: boolean,
) {
  const next = new Map(prev);
  for (const k of keys) {
    if (on) {
      const row = rows.find((r) => rowKey(r) === k);
      if (row) next.set(k, row);
    } else next.delete(k);
  }
  return next;
}
