"use client";

import { useState } from "react";
import { AlertTriangle, ArrowRight, Check, CircleCheck, Download, FileSpreadsheet, FileText, Sheet, Upload, X } from "lucide-react";
import { api, invalidate, post, useApi, type ApiError } from "@/lib/api";
import { Button, Field, Input, Segmented, Select } from "@/components/ui/controls";
import { ChosenFile, FileDrop } from "@/components/ui/file-drop";
import { Dialog, useToast } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { MoreMenu, type MenuAction } from "@/components/ui/more-menu";

type DatasetInfo = { key: string; label: string; importable: boolean; note: string | null; match_keys: string[]; fields: { name: string; label: string; type: string; required: boolean; importable: boolean; choices: string[] | null; help: string | null }[] };
type Issue = { sheet: string; row: number; column: string | null; value: string; error: string; expected: string | null; suggestion: string | null };
type Job = {
  id: number;
  reference: string;
  dataset: string;
  dataset_label: string;
  mode: "create" | "update" | "upsert";
  filename: string;
  sheet: string;
  sheets: string[];
  headers: string[];
  mapping: Record<string, string>;
  status: "uploaded" | "validated" | "committed" | "failed";
  summary: { rows?: number; create?: number; update?: number; error?: number; duplicate_of?: string | null; suggestions?: Record<string, { field: string | null; confidence: number; ambiguous: boolean }> };
  issues: Issue[];
  issue_count: number;
  results: { create?: number; update?: number; error?: number };
  preview?: unknown[];
};

/** Download a protected file through the API (cookies), keeping the server's filename. */
export async function download(url: string, fallback: string) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error((body as { detail?: string })?.detail ?? "Download failed");
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallback;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/**
 * Import and Export for a module page, plus any page-specific secondary actions (`extra`),
 * all inside one "More actions" menu next to the page's primary button.
 */
export function DataTools({ dataset, statuses, extra = [] }: { dataset: string; statuses?: { value: string; label: string }[]; extra?: MenuAction[] }) {
  const catalogue = useApi<DatasetInfo[]>("/api/v1/datasets");
  const ds = catalogue.data?.find((d) => d.key === dataset);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const actions: MenuAction[] = [
    ...(ds?.importable ? [{ label: "Import from Excel or CSV", icon: Upload, onSelect: () => setImporting(true) }] : []),
    ...(ds ? [{ label: "Export", icon: Download, hint: "Excel, CSV or PDF", onSelect: () => setExporting(true) }] : []),
    ...extra,
  ];
  return (
    <>
      <MoreMenu actions={actions} />
      {ds && importing && <ImportWizard ds={ds} onClose={() => setImporting(false)} />}
      {ds && <ExportDialog open={exporting} onClose={() => setExporting(false)} ds={ds} statuses={statuses} />}
    </>
  );
}

/* ---------------------------------------------------------------- export */

function ExportDialog({ open, onClose, ds, statuses }: { open: boolean; onClose: () => void; ds: DatasetInfo; statuses?: { value: string; label: string }[] }) {
  const toast = useToast();
  const [format, setFormat] = useState<"xlsx" | "csv" | "pdf">("xlsx");
  const [status, setStatus] = useState("");
  const [company, setCompany] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    const sp = new URLSearchParams({ format });
    if (status) sp.set("status", status);
    if (company) sp.set("company", company);
    if (from) sp.set("date_from", from);
    if (to) sp.set("date_to", to);
    try {
      await download(`/api/v1/exports/${ds.key}?${sp}`, `${ds.key}.${format}`);
      toast("Export ready");
      onClose();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Export ${ds.label}`}
      description="Only records you're allowed to see are included. Every export is logged."
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" icon={Download} busy={busy} onClick={go}>
            Download
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Format">
          <Segmented<"xlsx" | "csv" | "pdf">
            label="Format"
            value={format}
            onChange={setFormat}
            options={[
              { value: "xlsx", label: "Excel", icon: FileSpreadsheet },
              { value: "csv", label: "CSV", icon: Sheet },
              { value: "pdf", label: "PDF", icon: FileText },
            ]}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          {statuses && (
            <Field label="Status" htmlFor="ex-status">
              <Select id="ex-status" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">All</option>
                {statuses.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Company" htmlFor="ex-company">
            <Select id="ex-company" value={company} onChange={(e) => setCompany(e.target.value)}>
              <option value="">All my companies</option>
              <option value="GPI">Getmeds Philippines Inc.</option>
              <option value="2MG">2MG</option>
            </Select>
          </Field>
          <Field label="From" htmlFor="ex-from">
            <Input id="ex-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To" htmlFor="ex-to">
            <Input id="ex-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- import wizard */

const STEPS = ["Upload", "Match columns", "Check", "Done"] as const;

export function ImportWizard({ ds, onClose }: { ds: DatasetInfo; onClose: () => void }) {
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"create" | "update" | "upsert">("create");
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [matchKey, setMatchKey] = useState(ds.match_keys[0] ?? "");
  const [skip, setSkip] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const fields = ds.fields.filter((f) => f.importable);

  async function doUpload() {
    if (!file) return;
    setBusy(true);
    setErr(undefined);
    try {
      const fd = new FormData();
      fd.set("dataset", ds.key);
      fd.set("mode", mode);
      fd.set("file", file);
      const j = await api<Job>("/api/v1/imports", { method: "POST", body: fd });
      setJob(j);
      setMapping(j.mapping);
      setStep(1);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }
  async function doSheet(sheet: string) {
    if (!job) return;
    const j = await post<Job>(`/api/v1/imports/${job.id}/sheet`, { sheet });
    setJob(j);
    setMapping(j.mapping);
  }
  async function doValidate() {
    if (!job) return;
    setBusy(true);
    setErr(undefined);
    try {
      const j = await post<Job>(`/api/v1/imports/${job.id}/validate`, { mapping, match_key: mode === "create" ? null : matchKey || null });
      setJob(j);
      setStep(2);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }
  async function doCommit() {
    if (!job) return;
    setBusy(true);
    setErr(undefined);
    try {
      const j = await post<Job>(`/api/v1/imports/${job.id}/commit`, { skip_invalid: skip });
      setJob(j);
      setStep(3);
      toast(`Imported · ${j.reference}`);
      invalidate();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const required = fields.filter((f) => f.required).map((f) => f.name);
  const mapped = new Set(Object.values(mapping).filter(Boolean));
  const missingRequired = mode === "create" ? required.filter((r) => !mapped.has(r)) : [];
  const s = job?.summary ?? {};

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      title={`Import ${ds.label}`}
      footer={
        <>
          {step === 0 && (
            <>
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" icon={ArrowRight} busy={busy} disabled={!file} onClick={doUpload}>
                Upload and continue
              </Button>
            </>
          )}
          {step === 1 && (
            <>
              <Button onClick={() => setStep(0)}>Back</Button>
              <Button variant="primary" icon={ArrowRight} busy={busy} disabled={missingRequired.length > 0} onClick={doValidate}>
                Check the data
              </Button>
            </>
          )}
          {step === 2 && (
            <>
              <Button onClick={() => setStep(1)}>Back to columns</Button>
              <Button variant="primary" icon={Check} busy={busy} disabled={!((s.create ?? 0) + (s.update ?? 0)) || (Boolean(s.error) && !skip)} onClick={doCommit}>
                Import {(s.create ?? 0) + (s.update ?? 0)} row{(s.create ?? 0) + (s.update ?? 0) === 1 ? "" : "s"}
              </Button>
            </>
          )}
          {step === 3 && (
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          )}
        </>
      }
    >
      <ol className="mb-5 flex gap-2 text-[12.5px]" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li key={label} className={cn("flex items-center gap-1.5", i === step ? "font-bold text-ink" : i < step ? "text-ink-2" : "text-ink-3")}>
            <span className={cn("flex size-5 items-center justify-center rounded-full text-[11px]", i < step ? "bg-ink text-white" : i === step ? "ring-2 ring-accent" : "ring-1 ring-edge")} aria-hidden="true">
              {i < step ? <Check className="size-3" strokeWidth={3} /> : i + 1}
            </span>
            <span className={cn(i !== step && "hidden sm:inline")}>{label}</span>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-ctl)] bg-canvas p-3 text-[13.5px]">
            <FileSpreadsheet className="size-5 text-ink-2" strokeWidth={1.6} aria-hidden="true" />
            <span className="flex-1">Start from the official template so columns match automatically.</span>
            <Button size="sm" icon={Download} onClick={() => download(`/api/v1/datasets/${ds.key}/template`, `${ds.key}-template.xlsx`)}>
              Excel template
            </Button>
          </div>
          {ds.match_keys.length > 0 && (
            <Field label="Import mode">
              <Segmented<"create" | "update" | "upsert">
                label="Mode"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "create", label: "Add new" },
                  { value: "update", label: "Update existing" },
                  { value: "upsert", label: "Add or update" },
                ]}
              />
            </Field>
          )}
          <FileDrop accept=".xlsx,.csv" multiple={false} camera={false} title="Excel (.xlsx) or CSV file" hint="up to 10 MB and 5,000 rows. Formulas and macros are never run." inputLabel="Excel or CSV file" onFiles={(f) => setFile(f[0])}>
            {file && <ChosenFile file={file} onRemove={() => setFile(null)} />}
          </FileDrop>
          {ds.note && <p className="text-[12.5px] text-ink-3">{ds.note}</p>}
        </div>
      )}

      {step === 1 && job && (
        <div className="flex flex-col gap-4">
          <p className="text-[13.5px] text-ink-2">
            <span className="font-medium text-ink">{job.filename}</span> · {s.rows ?? 0} rows. Columns are matched automatically. Review any column marked “Verify”.
          </p>
          {s.duplicate_of && (
            <p className="flex items-center gap-2 rounded-[var(--radius-ctl)] bg-danger-soft px-3 py-2 text-[13px] text-danger">
              <AlertTriangle className="size-4 shrink-0" strokeWidth={2} aria-hidden="true" /> This exact file was already imported ({s.duplicate_of}).
            </p>
          )}
          {job.sheets.length > 1 && (
            <Field label="Worksheet" htmlFor="sheet">
              <Select id="sheet" value={job.sheet} onChange={(e) => doSheet(e.target.value)}>
                {job.sheets.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </Select>
            </Field>
          )}
          {mode !== "create" && ds.match_keys.length > 1 && (
            <Field label="Match existing records by" htmlFor="mk">
              <Select id="mk" value={matchKey} onChange={(e) => setMatchKey(e.target.value)}>
                {ds.match_keys.map((k) => (
                  <option key={k} value={k}>
                    {ds.fields.find((f) => f.name === k)?.label ?? k}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <ul className="divide-y divide-line rounded-[var(--radius-ctl)] border border-line">
            {job.headers.filter(Boolean).map((h) => {
              const sug = s.suggestions?.[h];
              return (
                <li key={h} className="grid items-center gap-2 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_20px_minmax(0,1.2fr)]">
                  <span className="min-w-0 truncate text-[13.5px] font-medium">{h}</span>
                  <ArrowRight className="hidden size-4 text-mute sm:block" strokeWidth={1.75} aria-hidden="true" />
                  <span className="flex items-center gap-2">
                    <Select aria-label={`Field for ${h}`} value={mapping[h] ?? ""} onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}>
                      <option value="">Don&apos;t import</option>
                      {fields.map((f) => (
                        <option key={f.name} value={f.name}>
                          {f.label}
                          {f.required ? " *" : ""}
                        </option>
                      ))}
                    </Select>
                    {sug?.ambiguous && mapping[h] === sug.field && <span className="shrink-0 text-[11.5px] font-medium text-ink">Verify</span>}
                  </span>
                </li>
              );
            })}
          </ul>
          {missingRequired.length > 0 && (
            <p role="alert" className="text-[13px] text-danger">
              Match a column to: {missingRequired.map((r) => fields.find((f) => f.name === r)?.label).join(", ")}
            </p>
          )}
        </div>
      )}

      {step === 2 && job && (
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-3 gap-2 text-center">
            {[
              ["New", s.create ?? 0],
              ["Updates", s.update ?? 0],
              ["With errors", s.error ?? 0],
            ].map(([k, v]) => (
              <div key={k as string} className={cn("rounded-[var(--radius-ctl)] border p-3", k === "With errors" && (v as number) > 0 ? "border-danger/40 text-danger" : "border-line")}>
                <dt className="text-[12px] font-medium text-ink-3">{k}</dt>
                <dd className="tabular text-[22px] font-bold">{v}</dd>
              </div>
            ))}
          </dl>
          {job.issue_count > 0 && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13.5px] font-medium">Problems found</p>
                <span className="flex gap-2">
                  <Button size="sm" icon={Download} onClick={() => download(`/api/v1/imports/${job.id}/errors`, "errors.xlsx")}>
                    Error report
                  </Button>
                  <Button size="sm" variant="ghost" icon={FileSpreadsheet} onClick={() => download(`/api/v1/imports/${job.id}/errors?format=annotated`, "annotated.xlsx")}>
                    Annotated file
                  </Button>
                </span>
              </div>
              <ul className="max-h-[240px] divide-y divide-line overflow-y-auto rounded-[var(--radius-ctl)] border border-line text-[13px]">
                {job.issues.slice(0, 100).map((i, n) => (
                  <li key={n} className="flex gap-3 px-3 py-2">
                    <span className="tabular w-14 shrink-0 text-ink-3">Row {i.row}</span>
                    <span className="min-w-0">
                      <span className="font-medium">{i.column ?? "Row"}</span>: {i.error}
                      {i.value ? <span className="text-ink-3"> (“{i.value}”)</span> : null}
                      {(i.suggestion || i.expected) && <span className="block text-[12px] text-ink-3">{i.suggestion ? `Try: ${i.suggestion}` : `Expected: ${i.expected}`}</span>}
                    </span>
                  </li>
                ))}
              </ul>
              {((s.create ?? 0) + (s.update ?? 0)) > 0 && (
                <label className="flex items-center gap-2.5 text-[13.5px]">
                  <input type="checkbox" className="size-4 accent-[#111]" checked={skip} onChange={(e) => setSkip(e.target.checked)} />
                  Import the good rows and skip the {s.error} with errors
                </label>
              )}
            </>
          )}
          {job.issue_count === 0 && (
            <p className="flex items-center gap-2 text-[14px]">
              <CircleCheck className="size-5" strokeWidth={1.75} aria-hidden="true" /> Everything checks out.
            </p>
          )}
        </div>
      )}

      {step === 3 && job && (
        <div className="flex flex-col items-center py-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-ink text-white" aria-hidden="true">
            <Check className="size-6" strokeWidth={2.5} />
          </span>
          <p className="mt-4 text-[17px] font-bold">Import complete</p>
          <p className="mt-1 text-[14px] text-ink-2">
            {job.results.create ?? 0} added · {job.results.update ?? 0} updated{job.results.error ? ` · ${job.results.error} skipped` : ""}
          </p>
          <p className="tabular mt-1 text-[12.5px] text-ink-3">{job.reference}</p>
        </div>
      )}

      {err && (
        <p role="alert" className="mt-4 flex items-start gap-2 text-[13.5px] text-danger">
          <X className="mt-0.5 size-4 shrink-0" strokeWidth={2} aria-hidden="true" />
          {err}
        </p>
      )}
    </Dialog>
  );
}
