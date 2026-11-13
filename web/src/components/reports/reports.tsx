"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ChartColumn, Download, FilePlus2, FileSpreadsheet, FileText, History, Search, Sheet } from "lucide-react";
import { fmtDate, fmtDateTime, post, qs, useApi, type ApiError, type Person } from "@/lib/api";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { Button, Field, Input, Select } from "@/components/ui/controls";
import { EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { DocumentsRegister } from "@/components/documents/documents";
import { download } from "@/components/io/data-tools";
import { cn } from "@/lib/cn";

type Entry = { key: string; module: string; title: string; description: string; uses_dates: boolean; uses_within: boolean };
type Result = { key: string; title: string; module: string; description: string; columns: { key: string; label: string; kind: string }[]; rows: Record<string, unknown>[]; total_rows: number; totals: Record<string, unknown> | null };

const peso = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : `₱${Number(v).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

function cell(v: unknown, kind: string) {
  if (v === null || v === undefined || v === "") return "—";
  if (kind === "money") return peso(v);
  if (kind === "date") return String(v).length > 10 ? fmtDateTime(String(v)) : fmtDate(String(v));
  if (kind === "number") return Number(v).toLocaleString();
  return String(v);
}

type Tab = "reports" | "documents" | "imports";

export function ReportsHub() {
  const [tab, setTab] = useState<Tab>("reports");
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Reports" }]} />
      <PageHeader title="Reports" summary="Reports from live records, official documents, and data imports — in one place." icon={iconForHref("/administration/reports")} />
      <nav aria-label="Reports" className="no-scrollbar -mx-4 mt-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex min-w-max gap-1 border-b border-line">
          {(
            [
              ["reports", "Reports", ChartColumn],
              ["documents", "Documents", FileText],
              ["imports", "Data imports", History],
            ] as const
          ).map(([k, label, I]) => (
            <li key={k}>
              <button
                type="button"
                aria-current={tab === k ? "page" : undefined}
                onClick={() => setTab(k)}
                className={cn("-mb-px flex h-11 items-center gap-2 border-b-2 px-3 text-[14px]", tab === k ? "border-ink font-bold" : "border-transparent font-medium text-ink-3 hover:text-ink")}
              >
                <I className="size-4" strokeWidth={1.75} aria-hidden="true" />
                {label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="mt-6">
        {tab === "reports" && <ReportCatalogue />}
        {tab === "documents" && (
          <div className="flex flex-col gap-5">
            <PeriodReports />
            <DocumentsRegister />
          </div>
        )}
        {tab === "imports" && <ImportHistory />}
      </div>
    </PageFrame>
  );
}

function ReportCatalogue() {
  const cat = useApi<Entry[]>("/api/v1/reports");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Entry | null>(null);
  const groups = useMemo(() => {
    const m = new Map<string, Entry[]>();
    for (const r of cat.data ?? []) {
      if (q && !`${r.title} ${r.description} ${r.module}`.toLowerCase().includes(q.toLowerCase())) continue;
      m.set(r.module, [...(m.get(r.module) ?? []), r]);
    }
    return [...m.entries()];
  }, [cat.data, q]);
  if (open) return <ReportViewer entry={open} onBack={() => setOpen(null)} />;
  return (
    <div className="flex flex-col gap-5">
      <label className="relative block max-w-[480px]">
        <span className="sr-only">Search reports</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
        <Input type="search" placeholder="Search reports" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {!cat.data ? (
        <Panel>
          <SkeletonRows />
        </Panel>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {groups.map(([module, items]) => (
            <Panel key={module} title={module} meta={`${items.length}`}>
              <ul className="divide-y divide-line">
                {items.map((r) => (
                  <li key={r.key}>
                    <button type="button" onClick={() => setOpen(r)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-canvas sm:px-5">
                      <ChartColumn className="mt-0.5 size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block text-[14px] font-medium">{r.title}</span>
                        <span className="block text-[12.5px] text-ink-3">{r.description}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}

function ReportViewer({ entry, onBack }: { entry: Entry; onBack: () => void }) {
  const toast = useToast();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [within, setWithin] = useState("60");
  const [company, setCompany] = useState("");
  const params = qs({ date_from: entry.uses_dates ? from : undefined, date_to: entry.uses_dates ? to : undefined, within: entry.uses_within ? within : undefined, company });
  const r = useApi<Result>(`/api/v1/reports/${entry.key}${params}`);
  async function exp(format: string) {
    try {
      await download(`/api/v1/reports/${entry.key}/export${params}${params ? "&" : "?"}format=${format}`, `${entry.key}.${format}`);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" icon={ArrowLeft} onClick={onBack} className="-ml-3">
          All reports
        </Button>
        <div className="flex gap-2">
          <Button size="sm" icon={FileSpreadsheet} onClick={() => exp("xlsx")}>
            Excel
          </Button>
          <Button size="sm" variant="ghost" icon={Sheet} onClick={() => exp("csv")}>
            CSV
          </Button>
          <Button size="sm" variant="ghost" icon={FileText} onClick={() => exp("pdf")}>
            PDF
          </Button>
        </div>
      </div>
      <div>
        <h2 className="text-[20px] font-bold">{entry.title}</h2>
        <p className="mt-1 text-[14px] text-ink-2">{entry.description}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        {entry.uses_dates && (
          <>
            <Field label="From" htmlFor="r-from">
              <Input id="r-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </Field>
            <Field label="To" htmlFor="r-to">
              <Input id="r-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </Field>
          </>
        )}
        {entry.uses_within && (
          <Field label="Window" htmlFor="r-within">
            <Select id="r-within" value={within} onChange={(e) => setWithin(e.target.value)}>
              {["30", "60", "90", "180", "365"].map((d) => (
                <option key={d} value={d}>
                  Next {d} days
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Company" htmlFor="r-company">
          <Select id="r-company" value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">All my companies</option>
            <option value="GPI">Getmeds Philippines Inc.</option>
            <option value="2MG">2MG</option>
          </Select>
        </Field>
      </div>
      <Panel meta={r.data ? `${r.data.total_rows} rows` : undefined} title="Results">
        {r.error ? (
          <ErrorState message={r.error.message} onRetry={r.reload} />
        ) : !r.data ? (
          <SkeletonRows />
        ) : r.data.rows.length === 0 ? (
          <EmptyState icon={ChartColumn} title="No records found" body="No records match these settings." compact />
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead>
                <tr className="border-b border-ink bg-canvas text-left">
                  {r.data.columns.map((c) => (
                    <th key={c.key} scope="col" className={cn("px-3 py-2 font-bold text-ink-2 first:pl-5 last:pr-5", (c.kind === "money" || c.kind === "number") && "text-right")}>
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {r.data.rows.map((row, i) => (
                  <tr key={i} className="hover:bg-canvas">
                    {r.data!.columns.map((c) => (
                      <td key={c.key} className={cn("px-3 py-2 align-top first:pl-5 last:pr-5", (c.kind === "money" || c.kind === "number") && "tabular text-right")}>
                        {cell(row[c.key], c.kind)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              {r.data.totals && (
                <tfoot>
                  <tr className="border-t border-ink font-bold">
                    {r.data.columns.map((c, i) => (
                      <td key={c.key} className={cn("px-3 py-2 first:pl-5 last:pr-5", (c.kind === "money" || c.kind === "number") && "tabular text-right")}>
                        {i === 0 ? "Total" : c.key in r.data!.totals! ? cell(r.data!.totals![c.key], c.kind) : ""}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
        {r.data && r.data.total_rows > r.data.rows.length && <p className="border-t border-line px-5 py-2 text-[12.5px] text-ink-3">Showing the first {r.data.rows.length}. Export for all {r.data.total_rows} rows.</p>}
      </Panel>
    </div>
  );
}

const PERIOD_DOCS = [
  { key: "monthly_administrative_report", title: "Monthly Administrative Report" },
  { key: "executive_summary_report", title: "Executive Summary Report" },
  { key: "compliance_monitoring_report", title: "Compliance Monitoring Report" },
  { key: "contract_monitoring_report", title: "Contract Monitoring Report" },
];

function PeriodReports() {
  const toast = useToast();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [busy, setBusy] = useState<string | null>(null);
  async function make(key: string) {
    setBusy(key);
    try {
      const d = await post<{ url: string; control_number: string; title: string }>("/api/v1/documents", { template_key: key, related_id: Number(month.replace("-", "")), paper: "A4" });
      toast(`${d.title} · ${d.control_number}`);
      window.open(d.url, "_blank", "noopener");
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(null);
    }
  }
  return (
    <Panel title="Monthly reports">
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:px-5">
        <Field label="Month" htmlFor="pm" className="sm:w-[180px]">
          <Input id="pm" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </Field>
        <div className="flex flex-wrap gap-2">
          {PERIOD_DOCS.map((p) => (
            <Button key={p.key} size="sm" icon={FilePlus2} busy={busy === p.key} disabled={busy !== null} onClick={() => make(p.key)}>
              {p.title.replace(" Report", "")}
            </Button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

type JobRow = { id: number; reference: string; dataset_label: string; mode: string; filename: string; status: string; summary: { rows?: number }; results: { create?: number; update?: number; error?: number }; created_by: Person; created_at: string; issue_count: number };

function ImportHistory() {
  const toast = useToast();
  const data = useApi<JobRow[]>("/api/v1/imports");
  return (
    <Panel title="Recent imports" meta={data.data ? `${data.data.length}` : undefined}>
      {!data.data ? (
        <SkeletonRows />
      ) : data.data.length === 0 ? (
        <EmptyState icon={History} title="No imports yet" body="Use Import on a module (Assets, Inventory, Fleet, Compliance, Contracts, Tasks…) to bring in records from Excel or CSV." compact />
      ) : (
        <ul className="divide-y divide-line">
          {data.data.map((j) => (
            <li key={j.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:px-5">
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-medium">
                  {j.dataset_label} · <span className="font-normal text-ink-2">{j.filename}</span>
                </span>
                <span className="tabular block text-[12px] text-ink-3">
                  {j.reference} · {j.created_by.name} · {fmtDateTime(j.created_at)} · {j.status === "committed" ? `${j.results.create ?? 0} added, ${j.results.update ?? 0} updated${j.results.error ? `, ${j.results.error} skipped` : ""}` : j.status}
                </span>
              </span>
              {j.issue_count > 0 && (
                <Button size="sm" variant="ghost" icon={Download} onClick={() => download(`/api/v1/imports/${j.id}/errors`, "errors.xlsx").catch((e) => toast(e.message, "error"))}>
                  Error report
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
