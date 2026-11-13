"use client";

import Link from "next/link";
import { createElement, useEffect, useRef } from "react";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { findItem, itemHref, tabItems } from "@/lib/nav";
import { cn } from "@/lib/cn";

/**
 * Page frame for a live module group (Assets, Fleet…): one menu entry, with the
 * group's screens as tabs instead of a list of sidebar links.
 */
export function ModuleShell({
  group,
  item,
  title,
  summary,
  actions,
  children,
}: {
  group: string;
  item: string;
  title?: string;
  summary?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const route = findItem(group, item)!;
  // A filtered view (e.g. /fleet/registration-insurance) belongs to its parent screen's tab.
  const found = route.item.under ? findItem(group, route.item.under)! : route;
  const tab = found.item.slug;
  const href = itemHref(found.group, found.item);
  const current = useRef<HTMLAnchorElement>(null);
  // Phones scroll the tab strip; keep the current tab in view (without moving the page vertically).
  useEffect(() => {
    const el = current.current;
    const strip = el?.closest("nav");
    if (el && strip && strip.scrollWidth > strip.clientWidth) strip.scrollLeft = el.offsetLeft - (strip.clientWidth - el.offsetWidth) / 2;
  }, [tab]);
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: found.group.label, href: itemHref(found.group, tabItems(found.group)[0]) }, { label: title ?? found.item.label }]} />
      <PageHeader title={title ?? found.item.label} summary={summary ?? found.item.summary} icon={iconForHref(href)} actions={actions} />
      <div className="mt-6 lg:grid lg:grid-cols-[236px_minmax(0,1fr)] lg:items-start lg:gap-8">
        {/* Phones and tablets: a swipeable strip (scrollbar hidden). Desktop: a vertical sub-menu, so nothing overflows. */}
        <nav aria-label={found.group.label} className="no-scrollbar -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0 lg:sticky lg:top-20 lg:overflow-visible">
          <p className="mb-2 hidden px-3 text-[12px] font-medium text-ink-3 lg:block">{found.group.label}</p>
          <ul className="flex min-w-max gap-1 border-b border-line lg:min-w-0 lg:flex-col lg:gap-0.5 lg:border-b-0">
            {tabItems(found.group).map((i) => {
              const h = itemHref(found.group, i);
              const on = i.slug === tab;
              return (
                <li key={i.slug}>
                  <Link
                    ref={on ? current : undefined}
                    href={h}
                    aria-current={on ? "page" : undefined}
                    className={cn(
                      "-mb-px flex h-11 items-center gap-2 border-b-2 px-3 text-[14px] transition-colors duration-150",
                      "lg:mb-0 lg:h-auto lg:min-h-10 lg:py-2 lg:leading-snug lg:rounded-[var(--radius-ctl)] lg:border-b-0 lg:border-l-2 lg:rounded-l-none",
                      on ? "border-ink font-bold text-ink lg:bg-sheet" : "border-transparent font-medium text-ink-3 hover:text-ink lg:hover:bg-hover",
                    )}
                  >
                    {createElement(iconForHref(h), { className: "size-4 shrink-0", strokeWidth: 1.75, "aria-hidden": true })}
                    <span>{i.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-6 min-w-0 lg:mt-0">{children}</div>
      </div>
    </PageFrame>
  );
}
