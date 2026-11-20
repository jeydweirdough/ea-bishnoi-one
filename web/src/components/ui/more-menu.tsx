"use client";

import { createElement, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Ellipsis, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export type MenuAction = { label: string; icon: LucideIcon; onSelect: () => void; hint?: string };

/**
 * The page's secondary actions (Import, Export, settings) behind one "More actions" button,
 * so the header keeps a single labelled primary action.
 */
export function MoreMenu({ actions, label = "More actions" }: { actions: MenuAction[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const menu = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const id = useId();

  // Keep the menu on screen: line it up with the button's right edge (left edge if that fits better),
  // never past the screen edges, and open upwards when there's no room below.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const btn = root.current?.querySelector("button")?.getBoundingClientRect();
      const m = menu.current;
      if (!btn || !m) return;
      const gap = 8, edge = 12;
      const vw = document.documentElement.clientWidth, vh = window.innerHeight;
      const w = m.offsetWidth, h = m.offsetHeight;
      let left = btn.right - w;
      if (left < edge) left = btn.left;
      left = Math.max(edge, Math.min(left, vw - w - edge));
      let top = btn.bottom + gap;
      if (top + h > vh - edge && btn.top - gap - h >= edge) top = btn.top - gap - h;
      setPos({ left, top });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        root.current?.querySelector<HTMLButtonElement>("button[aria-haspopup]")?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    items.current[0]?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (actions.length === 0) return null;

  function onMenuKey(e: React.KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const list = items.current.filter(Boolean) as HTMLButtonElement[];
    const i = list.indexOf(document.activeElement as HTMLButtonElement);
    list[(i + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => {
          setPos(null);
          setOpen((o) => !o);
        }}
        className={cn(
          "flex size-11 items-center justify-center rounded-[var(--radius-ctl)] border bg-sheet text-ink-2 transition-colors duration-150 hover:border-edge hover:text-ink md:size-10",
          open ? "border-ink text-ink" : "border-line",
        )}
      >
        <Ellipsis className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          ref={menu}
          style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, opacity: 0 }}
          className="rise-in fixed z-50 w-max min-w-[220px] max-w-[min(320px,calc(100vw-24px))] rounded-[var(--radius-panel)] border border-line bg-sheet p-1.5 shadow-[0_12px_32px_-12px_rgb(0_0_0/0.18)]"
        >
          {actions.map((a, i) => (
            <button
              key={a.label}
              ref={(el) => {
                items.current[i] = el;
              }}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                a.onSelect();
              }}
              className="flex w-full items-start gap-3 rounded-[var(--radius-ctl)] px-3 py-2.5 text-left text-[14px] font-medium text-ink outline-none hover:bg-hover focus-visible:bg-hover"
            >
              {createElement(a.icon, { className: "mt-0.5 size-4 shrink-0 text-ink-2", strokeWidth: 1.75, "aria-hidden": true })}
              <span className="min-w-0">
                {a.label}
                {a.hint && <span className="tabular block text-[12.5px] font-normal text-ink-3">{a.hint}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
