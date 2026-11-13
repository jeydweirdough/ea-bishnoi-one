"use client";

import Link from "next/link";
import { ChevronRight, MessageSquareWarning, PackagePlus, type LucideIcon } from "lucide-react";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";

const CHOICES: { href: string; icon: LucideIcon; title: string; body: string; examples: string }[] = [
  {
    href: "/me/raise-concern",
    icon: MessageSquareWarning,
    title: "Report a problem",
    body: "Something is broken, unsafe or not working.",
    examples: "Leaking aircon, broken chair, no internet, repairs",
  },
  {
    href: "/me/request-supplies",
    icon: PackagePlus,
    title: "Request items",
    body: "You need supplies, equipment or a purchase.",
    examples: "Bond paper, toner, a monitor, a local purchase",
  },
];

/** One question instead of a menu: what do you need? */
export function NewRequestChooser() {
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "My requests", href: "/me/requests" }, { label: "New request" }]} />
      <div className="mx-auto max-w-[640px]">
        <h1 className="text-[26px] font-bold leading-tight tracking-[-0.02em] sm:text-[32px]">What do you need?</h1>
        <p className="mt-2 text-[15.5px] text-ink-2">Pick one. You can save it and finish later.</p>
        <ul className="mt-7 flex flex-col gap-3">
          {CHOICES.map((c) => (
            <li key={c.href}>
              <Link
                href={c.href}
                className="group flex items-center gap-4 rounded-[var(--radius-panel)] border border-line bg-sheet p-4 transition-[border-color,box-shadow] duration-150 hover:border-ink hover:shadow-[0_6px_20px_-12px_rgb(17_17_17/0.35)] sm:gap-5 sm:p-5"
              >
                <span className="flex size-14 shrink-0 items-center justify-center rounded-[14px] bg-ink text-white" aria-hidden="true">
                  <c.icon className="size-7" strokeWidth={1.6} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[17px] font-bold">{c.title}</span>
                  <span className="mt-0.5 block text-[14.5px] text-ink-2">{c.body}</span>
                  <span className="mt-1 block text-[13px] text-ink-3">{c.examples}</span>
                </span>
                <ChevronRight className="size-5 shrink-0 text-mute transition-[color,transform] duration-200 group-hover:translate-x-0.5 group-hover:text-ink" strokeWidth={1.75} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </PageFrame>
  );
}
