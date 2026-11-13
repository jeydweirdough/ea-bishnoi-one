"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

const PREVIEW = 6;

/** Splits "Priority — Low / Normal / High" into a name and its allowed values. */
function Field({ text }: { text: string }) {
  const [name, options] = text.split(" — ");
  return (
    <li className="flex min-h-11 flex-col justify-center gap-1.5 px-4 py-2.5 sm:px-5">
      <span className="text-[14px] leading-snug">{name}</span>
      {options && (
        <span className="flex flex-wrap gap-1">
          {options.split(" / ").map((o) => (
            <span key={o} className="rounded-[5px] bg-canvas px-1.5 py-px text-[12px] text-ink-2 ring-1 ring-line">
              {o}
            </span>
          ))}
        </span>
      )}
    </li>
  );
}

export function FieldList({ fields }: { fields: string[] }) {
  const [open, setOpen] = useState(false);
  const extra = fields.length - PREVIEW;
  const shown = open || extra <= 1 ? fields : fields.slice(0, PREVIEW);
  return (
    <>
      <ul className="grid divide-y divide-line sm:grid-cols-2 sm:divide-y-0 sm:[&>li]:border-b sm:[&>li]:border-line sm:[&>li:nth-child(odd)]:border-r">
        {shown.map((f) => (
          <Field key={f} text={f} />
        ))}
      </ul>
      {extra > 1 && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex min-h-11 w-full items-center justify-center gap-1.5 border-t border-line text-[13.5px] font-medium text-ink-2 transition-colors duration-150 hover:bg-canvas hover:text-ink sm:-mt-px"
        >
          {open ? "Show fewer" : `Show all ${fields.length} fields`}
          <ChevronDown className={cn("size-4 transition-transform duration-200", open && "rotate-180")} strokeWidth={1.75} />
        </button>
      )}
    </>
  );
}
