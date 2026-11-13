"use client";

import { Printer } from "lucide-react";
import { fmtDate, fmtDateTime, useApi } from "@/lib/api";
import type { Asset } from "./assets";
import { CONDITIONS } from "./assets";

/**
 * Printable Asset Issuance Form (A4 / Letter). Signature lines are blank on purpose:
 * the form never claims a signature. The in-app acknowledgement is stated as a fact
 * with its timestamp. The full document engine (control numbers, versions, PDF) is Phase 2.9.
 */
export function IssuanceForm({ id }: { id: number }) {
  const q = useApi<Asset & { events: { type: string; at: string }[] }>(`/api/v1/assets/${id}`);
  const a = q.data;
  if (q.error) return <p className="p-10 text-[14px]">{q.error.status === 404 ? "This asset isn't available to you." : q.error.message}</p>;
  if (!a) return <p className="p-10 text-[14px] text-ink-3">Preparing form…</p>;
  if (!a.holder) return <p className="p-10 text-[14px]">This asset is not issued to anyone, so there is no issuance form.</p>;
  const condition = CONDITIONS.find((c) => c.value === a.condition)?.label ?? a.condition;
  const rows: [string, string][] = [
    ["Asset tag", a.reference],
    ["Description", a.name],
    ["Category", a.category],
    ["Brand / model", [a.brand, a.model].filter(Boolean).join(" ") || "—"],
    ["Serial number", a.serial_number ?? "—"],
    ["Quantity", `${a.quantity} ${a.unit}`],
    ["Condition at issue", condition],
    ["Location", a.location ?? "—"],
  ];
  return (
    <div className="min-h-dvh bg-canvas py-8 print:bg-white print:py-0">
      <style>{`@page { size: A4; margin: 16mm; } @media print { .no-print { display: none !important; } }`}</style>
      <div className="no-print mx-auto mb-4 flex max-w-[794px] justify-end px-4">
        <button type="button" onClick={() => window.print()} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-ctl)] bg-ink px-4 text-[14px] font-medium text-white">
          <Printer className="size-4" strokeWidth={1.75} aria-hidden="true" />
          Print or save as PDF
        </button>
      </div>
      <article className="mx-auto max-w-[794px] bg-white px-12 py-10 text-[12.5px] leading-relaxed text-ink shadow-[var(--shadow-float)] print:max-w-none print:p-0 print:shadow-none">
        <header className="flex items-start justify-between border-b-2 border-ink pb-4">
          <div>
            <p className="text-[16px] font-bold">{a.company.name}</p>
            <p className="text-ink-3">Executive Admin · Corporate Services</p>
          </div>
          <div className="text-right">
            <p className="tabular font-medium">Control no. {a.reference}-ISS</p>
            <p className="text-ink-3">Issued {fmtDate(a.date_issued)}</p>
          </div>
        </header>
        <h1 className="mt-6 text-center text-[18px] font-bold tracking-[0.04em]">ASSET ISSUANCE FORM</h1>

        <section className="mt-6 grid grid-cols-2 gap-x-8 gap-y-1">
          <p>
            <span className="text-ink-3">Issued to:</span> <span className="font-medium">{a.holder.name}</span>
          </p>
          <p>
            <span className="text-ink-3">Employee ID:</span> <span className="tabular font-medium">{a.holder.employee_no}</span>
          </p>
          <p>
            <span className="text-ink-3">Department:</span> <span className="font-medium">{a.department?.name ?? a.holder.department ?? "—"}</span>
          </p>
          <p>
            <span className="text-ink-3">Date issued:</span> <span className="font-medium">{fmtDate(a.date_issued)}</span>
          </p>
        </section>

        <table className="mt-6 w-full border-collapse">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-line">
                <th scope="row" className="w-[34%] py-2 pr-4 text-left font-medium text-ink-3">
                  {k}
                </th>
                <td className="py-2">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {a.purpose && (
          <section className="mt-5">
            <p className="font-medium">Purpose</p>
            <p className="text-ink-2">{a.purpose}</p>
          </section>
        )}

        <p className="mt-6 text-ink-2">
          I acknowledge receipt of the asset described above in the stated condition. I will use it for company purposes, take reasonable care of it, report any
          damage or loss promptly, and return it on request or when I leave the company.
        </p>
        <p className="mt-2 text-ink-3">
          {a.acknowledged_at ? `Receipt acknowledged in Executive Admin on ${fmtDateTime(a.acknowledged_at)}.` : "Receipt not yet acknowledged in Executive Admin."}
        </p>

        <section className="mt-14 grid grid-cols-2 gap-12">
          {[
            ["Issued by", a.issued_by?.name ?? "", a.issued_by?.designation ?? "Executive Admin"],
            ["Received by", a.holder.name, a.holder.designation ?? ""],
          ].map(([role, name, title]) => (
            <div key={role}>
              <div className="h-12 border-b border-ink" />
              <p className="mt-1.5 font-medium">{name || " "}</p>
              <p className="text-ink-3">{title}</p>
              <p className="mt-1 text-[11.5px] font-medium tracking-wide text-ink-3 uppercase">{role} · Signature over printed name / date</p>
            </div>
          ))}
        </section>

        <footer className="mt-12 flex justify-between border-t border-line pt-3 text-[11px] text-ink-3">
          <span>Generated {fmtDateTime(new Date().toISOString())} from Executive Admin</span>
          <span>Page 1 of 1</span>
        </footer>
      </article>
    </div>
  );
}
