"use client";

import { useRouter } from "next/navigation";
import { createElement, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, CornerDownLeft, Search } from "lucide-react";
import { searchIndex, type SearchEntry } from "@/lib/nav";
import { iconForHref } from "@/components/icons";
import { cn } from "@/lib/cn";
import { useShell } from "./shell-context";

function rank(entries: SearchEntry[], query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return entries.filter((e) => e.context === "Group" || e.context === "Self-service" || e.context === "Approver");
  const scored: { e: SearchEntry; s: number }[] = [];
  for (const e of entries) {
    const label = e.label.toLowerCase();
    const code = e.code.toLowerCase();
    let s = -1;
    if (code === q) s = 100;
    else if (code.startsWith(q)) s = 90;
    else if (label.startsWith(q)) s = 80;
    else if (label.split(/[\s&/-]+/).some((w) => w.startsWith(q))) s = 70;
    else if (label.includes(q)) s = 60;
    else if (e.context.toLowerCase().includes(q)) s = 40;
    else if (e.summary.toLowerCase().includes(q)) s = 20;
    if (s >= 0) scored.push({ e, s });
  }
  return scored.sort((a, b) => b.s - a.s).map((x) => x.e);
}

function ResultIcon({ href }: { href: string }) {
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-[8px] bg-canvas text-ink-2 ring-1 ring-line" aria-hidden="true">
      {createElement(iconForHref(href), { className: "size-4", strokeWidth: 1.6 })}
    </span>
  );
}

export function CommandPalette() {
  const { session, paletteOpen, setPaletteOpen } = useShell();
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const entries = useMemo(() => (session ? searchIndex(session.role, session.approver) : []), [session]);
  const results = useMemo(() => rank(entries, query).slice(0, 40), [entries, query]);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (paletteOpen && !d.open) {
      d.showModal();
      requestAnimationFrame(() => input.current?.focus());
    }
    if (!paletteOpen && d.open) d.close();
  }, [paletteOpen]);

  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const go = (entry?: SearchEntry) => {
    if (!entry) return;
    setPaletteOpen(false);
    router.push(entry.href);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[cursor]);
    }
  };

  return (
    <dialog
      ref={dialog}
      onClose={() => {
        setPaletteOpen(false);
        setQuery("");
        setCursor(0);
      }}
      onClick={(e) => e.target === e.currentTarget && setPaletteOpen(false)}
      aria-label="Search modules"
      className="m-0 mx-auto mt-0 h-dvh max-h-none w-full max-w-none bg-sheet p-0 text-ink backdrop:bg-ink/60 backdrop:backdrop-blur-[2px] open:animate-[fade-in_160ms_var(--ease-out-expo)] md:mt-[12vh] md:h-auto md:max-h-[min(560px,76vh)] md:max-w-[640px] md:rounded-[14px] md:border md:border-line md:shadow-[var(--shadow-float)]"
    >
      <div className="flex h-full flex-col md:max-h-[min(560px,76vh)]">
        <div className="flex shrink-0 items-center gap-3 border-b border-line px-4 pt-[env(safe-area-inset-top)]">
          <Search className="size-5 shrink-0 text-ink-3" strokeWidth={1.75} />
          <input
            ref={input}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="Search modules, groups or codes like EA-04"
            aria-label="Search modules"
            aria-controls="palette-results"
            aria-activedescendant={results[cursor] ? `palette-${cursor}` : undefined}
            role="combobox"
            aria-expanded="true"
            autoComplete="off"
            spellCheck={false}
            className="h-14 flex-1 bg-transparent text-[16px] font-medium outline-none placeholder:font-normal placeholder:text-ink-3 focus-visible:shadow-none focus-visible:outline-none"
          />
          <button
            type="button"
            onClick={() => setPaletteOpen(false)}
            className="rounded-[6px] border border-line px-2 py-1 text-[12px] font-medium text-ink-3 hover:text-ink"
          >
            Esc
          </button>
        </div>

        <ul ref={list} id="palette-results" role="listbox" className="flex-1 overflow-y-auto overscroll-contain p-2">
          {results.length === 0 && (
            <li className="px-3 py-10 text-center">
              <p className="text-[15px] font-bold">No module matches “{query}”</p>
              <p className="mt-1 text-[13.5px] text-ink-3">Try a group name like “Fleet”, or a code like EA-05.</p>
            </li>
          )}
          {results.map((r, i) => (
            <li
              key={r.href}
              id={`palette-${i}`}
              data-index={i}
              role="option"
              aria-selected={i === cursor}
              onMouseMove={() => setCursor(i)}
              onClick={() => go(r)}
              style={{ animationDelay: `${Math.min(i, 10) * 18}ms` }}
              className={cn(
                "rise-in flex cursor-pointer items-center gap-3 rounded-[var(--radius-ctl)] px-3 py-2.5",
                i === cursor ? "bg-canvas shadow-[0_0_0_1px_var(--color-line)]" : "",
              )}
            >
              <ResultIcon href={r.href} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">{r.label}</span>
                <span className="block truncate text-[12.5px] text-ink-3">
                  {r.context === "Group" ? r.summary : r.context}
                </span>
              </span>
              <span className="tabular hidden shrink-0 text-[11.5px] text-mute sm:inline">{r.code}</span>
              {i === cursor && <CornerDownLeft className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} />}
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-4 border-t border-line px-4 py-2.5 text-[12px] text-ink-3 md:flex">
          <span className="inline-flex items-center gap-1">
            <kbd className="inline-flex items-center gap-0.5 text-ink-2">
              <ArrowUp className="size-3.5" strokeWidth={1.75} aria-label="Up" />
              <ArrowDown className="size-3.5" strokeWidth={1.75} aria-label="Down" />
            </kbd>
            to move
          </span>
          <span>
            <kbd className="font-sans font-medium text-ink-2">Enter</kbd> to open
          </span>
          <span className="ml-auto tabular">{results.length} results</span>
        </div>
      </div>
    </dialog>
  );
}
