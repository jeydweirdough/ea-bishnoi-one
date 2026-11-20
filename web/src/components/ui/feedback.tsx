"use client";

import Link from "next/link";
import { createContext, use, useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, CircleCheck, CircleAlert, RotateCw, X, type LucideIcon } from "lucide-react";
import { IconTile } from "@/components/icons";
import { Button } from "./controls";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- states */

export function EmptyState({
  icon,
  title,
  body,
  action,
  compact,
}: {
  icon: LucideIcon;
  title: string;
  body?: string;
  action?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 text-center", compact ? "py-8" : "py-14")}>
      <IconTile icon={icon} size={compact ? "md" : "lg"} />
      <h3 className="mt-4 text-[15px] font-bold">{title}</h3>
      {body && <p className="mt-1.5 max-w-[44ch] text-[13.5px] leading-relaxed text-ink-3">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-12 text-center">
      <IconTile icon={CircleAlert} size="lg" />
      <h3 className="mt-4 text-[15px] font-bold">Couldn&apos;t load this</h3>
      <p className="mt-1.5 max-w-[44ch] text-[13.5px] leading-relaxed text-ink-3">{message}</p>
      {onRetry && (
        <Button className="mt-5" icon={RotateCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <ul aria-hidden="true" className="divide-y divide-line">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className="flex items-center gap-4 px-4 py-4 sm:px-5">
          <span className="size-10 shrink-0 rounded-[10px] bg-line/70" />
          <span className="flex-1 space-y-2">
            <span className="block h-3 w-1/2 rounded-full bg-line/80" />
            <span className="block h-2.5 w-1/3 rounded-full bg-line/60" />
          </span>
          <span className="h-6 w-20 rounded-full bg-line/60" />
        </li>
      ))}
    </ul>
  );
}

export function Panel({ title, meta, children, className, actions }: { title?: string; meta?: React.ReactNode; children: React.ReactNode; className?: string; actions?: React.ReactNode }) {
  return (
    <section className={cn("overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet", className)}>
      {title && (
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-line px-4 py-2.5 sm:px-5">
          <h2 className="text-[14.5px] font-bold">{title}</h2>
          <div className="flex items-center gap-2">
            {meta && <span className="tabular shrink-0 text-[12.5px] text-ink-3">{meta}</span>}
            {actions}
          </div>
        </div>
      )}
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------- dialog */

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("textarea, input, select, button[data-autofocus]");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && ref.current) {
        const els = Array.from(ref.current.querySelectorAll<HTMLElement>("button, input, textarea, select, a[href]")).filter((el) => !el.hasAttribute("disabled"));
        if (!els.length) return;
        const [a, b] = [els[0], els[els.length - 1]];
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          b.focus();
        } else if (!e.shiftKey && document.activeElement === b) {
          e.preventDefault();
          a.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-6">
      {/* Figure-ground: the page behind drops well back, so the dialog is the one thing to look at. */}
      <div className="fade-in absolute inset-0 bg-ink/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "sheet-up relative flex max-h-[92dvh] w-full flex-col rounded-t-[16px] bg-sheet shadow-[var(--shadow-float)] sm:rounded-[var(--radius-panel)]",
          wide ? "sm:max-w-[640px]" : "sm:max-w-[460px]",
        )}
      >
        <div className="flex shrink-0 items-start gap-3 px-5 pb-2 pt-5">
          <div className="min-w-0 flex-1">
            <h2 className="text-[17px] font-bold leading-snug">{title}</h2>
            {description && <p className="mt-1 text-[13.5px] leading-relaxed text-ink-3">{description}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="-mr-2 -mt-1 flex size-10 items-center justify-center rounded-[var(--radius-ctl)] text-ink-3 hover:bg-hover hover:text-ink">
            <X className="size-5" strokeWidth={1.75} />
          </button>
        </div>
        {children && <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">{children}</div>}
        {footer && <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-line px-5 py-4 pb-[calc(16px+env(safe-area-inset-bottom))] sm:flex-row sm:justify-end sm:pb-4">{footer}</div>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- toast */

type Toast = { id: number; message: string; tone: "ok" | "error" };
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts([{ id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastContext value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+12px)] z-[80] flex flex-col items-center gap-2 px-4 lg:bottom-6"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className="rise-in pointer-events-auto flex max-w-[440px] items-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink px-4 py-3 text-[14px] text-white shadow-[var(--shadow-float)]"
          >
            {t.tone === "ok" ? (
              <CircleCheck className="size-4 shrink-0 text-accent" strokeWidth={2} aria-hidden="true" />
            ) : (
              <CircleAlert className="size-4 shrink-0 text-[#ff9b8f]" strokeWidth={2} aria-hidden="true" />
            )}
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext>
  );
}

export const useToast = () => use(ToastContext);

/* ---------------------------------------------------------------- pager */

export function Pager({ page, pageSize, total, onPage, onPageSize, sizes = [10, 25, 50, 100] }: { page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (n: number) => void; sizes?: number[] }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= (onPageSize ? Math.min(...sizes) : pageSize)) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  if (!onPageSize)
    return (
      <nav aria-label="Pagination" className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 sm:px-5">
        <p className="tabular text-[13px] text-ink-3">
          {from}–{to} of {total}
        </p>
        <div className="flex gap-2">
          <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            Previous
          </Button>
          <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
            Next
          </Button>
        </div>
      </nav>
    );
  const nav: [LucideIcon, string, number, boolean][] = [
    [ChevronsLeft, "First page", 1, page <= 1],
    [ChevronLeft, "Previous page", page - 1, page <= 1],
    [ChevronRight, "Next page", page + 1, page >= pages],
    [ChevronsRight, "Last page", pages, page >= pages],
  ];
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 sm:px-5">
      <p className="tabular text-[13px] text-ink-3">
        {from}–{to} of {total}
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-2 text-[13px] text-ink-2">
          Rows per page
          <select
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            className="h-9 rounded-[var(--radius-ctl)] border border-edge bg-sheet px-2 text-[13px] text-ink"
          >
            {sizes.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <span className="tabular text-[13px] font-medium">
          Page {page} of {pages}
        </span>
        <span className="flex gap-1">
          {nav.map(([Icon, label, to, off]) => (
            <button
              key={label}
              type="button"
              aria-label={label}
              disabled={off}
              onClick={() => onPage(to)}
              className="flex size-9 items-center justify-center rounded-[var(--radius-ctl)] border border-edge bg-sheet text-ink hover:bg-canvas disabled:opacity-40"
            >
              <Icon className="size-4" strokeWidth={1.75} />
            </button>
          ))}
        </span>
      </div>
    </nav>
  );
}

/* ---------------------------------------------------------------- count strip */

/**
 * Live counts as one quiet strip instead of a wall of stat cards. Each count links to its list.
 * On phones the counts are a row of cards that scrolls sideways, sized so the next card is cut
 * off at the edge: a half-shown card says "there is more, swipe".
 */
export function CountStrip({ items }: { items: { icon: LucideIcon; label: string; value?: number | string; href: string; danger?: boolean; onClick?: () => void }[] }) {
  return (
    <ul className="no-scrollbar -mx-4 flex snap-x snap-mandatory scroll-px-4 gap-2 overflow-x-auto px-4 sm:mx-0 sm:snap-none sm:gap-0 sm:overflow-hidden sm:rounded-[var(--radius-panel)] sm:border sm:border-line sm:bg-sheet sm:px-0 sm:divide-x sm:divide-line">
      {items.map(({ icon: Icon, label, value, href, danger, onClick }) => (
        <li key={label} className="w-[42%] min-w-[136px] shrink-0 snap-start overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet sm:w-auto sm:min-w-0 sm:flex-1 sm:rounded-none sm:border-0">
          <Link
            href={href}
            onClick={onClick && ((e) => (e.preventDefault(), onClick()))}
            className="flex h-full items-center gap-3 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas"
          >
            <Icon className={cn("size-[18px] shrink-0", danger && value ? "text-danger" : "text-ink-3")} strokeWidth={1.75} aria-hidden="true" />
            <span className="min-w-0">
              <span className={cn("tabular block text-[20px] font-bold leading-none", danger && value ? "text-danger" : "")}>{value ?? "–"}</span>
              <span className="mt-1 block truncate text-[12.5px] text-ink-3">{label}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
