"use client";

import { useState } from "react";
import { Ban, FilePlus2, FileText, PenLine, RefreshCcw, Send, Upload } from "lucide-react";
import { api, fmtDateTime, invalidate, post, qs, useApi, type ApiError, type Person } from "@/lib/api";
import { Button, Chip, Field, Input, Select, Textarea } from "@/components/ui/controls";
import { Dialog, EmptyState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { useShell } from "@/components/shell/shell-context";
import { cn } from "@/lib/cn";

export type Doc = {
  id: number;
  control_number: string;
  version: number;
  template_key: string;
  title: string;
  group: string | null;
  related_type: string;
  related_id: number;
  related_ref: string | null;
  status: "draft" | "for_review" | "for_approval" | "approved" | "final" | "rejected" | "issued" | "signed" | "superseded" | "voided";
  signature_status: string;
  paper: string;
  generated_by: Person;
  generated_at: string;
  issued_at: string | null;
  void_reason: string | null;
  url: string;
};
type TemplateRow = { key: string; title: string; group: string; available: boolean; reason: string | null; latest: Doc | null };

export const DOC_STATUS: Record<Doc["status"], string> = {
  draft: "Draft",
  for_review: "For review",
  for_approval: "For approval",
  approved: "Approved",
  final: "Final",
  rejected: "Rejected",
  issued: "Issued",
  signed: "Signed",
  superseded: "Superseded",
  voided: "Voided",
};

export function DocStatus({ s }: { s: Doc["status"] }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center rounded-full border px-2 text-[11.5px] font-medium whitespace-nowrap",
        s === "signed" || s === "issued" ? "border-ink bg-ink text-white" : s === "approved" || s === "final" ? "border-ink" : s === "voided" || s === "rejected" ? "border-danger/30 bg-danger-soft text-danger" : "border-line bg-canvas text-ink-3",
      )}
    >
      {DOC_STATUS[s]}
    </span>
  );
}

/** Documents that can be produced from one record: generate, view, issue, signed copy, void. */
export function DocumentsPanel({ relatedType, relatedId, title = "Documents" }: { relatedType: string; relatedId: number; title?: string }) {
  const toast = useToast();
  const { me } = useShell();
  const staff = me?.role !== "employee";
  const q = useApi<TemplateRow[]>(`/api/v1/documents/templates${qs({ related_type: relatedType, related_id: relatedId })}`);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [paper, setPaper] = useState<"A4" | "Letter">("A4");
  const [signing, setSigning] = useState<Doc | null>(null);
  const [voiding, setVoiding] = useState<Doc | null>(null);
  const rows = q.data ?? [];
  const made = rows.filter((r) => r.latest);
  const available = rows.filter((r) => r.available);

  async function generate(key: string) {
    setBusy(key);
    try {
      const d = await post<Doc>("/api/v1/documents", { template_key: key, related_id: relatedId, paper });
      toast(`${d.title} · ${d.control_number}${d.version > 1 ? ` v${d.version}` : ""}`);
      window.open(d.url, "_blank", "noopener");
      q.reload();
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(null);
    }
  }
  async function issue(d: Doc) {
    try {
      await post(`/api/v1/documents/${d.id}/issue`);
      toast(`Issued · ${d.control_number}`);
      q.reload();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }

  if (!q.data || rows.length === 0) return null;
  return (
    <Panel
      title={title}
      meta={made.length ? `${made.length}` : undefined}
      actions={
        <Button size="sm" variant="ghost" icon={FilePlus2} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Create
        </Button>
      }
    >
      {open && (
        <div className="border-b border-line p-3 sm:px-5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-[12.5px] font-medium text-ink-3">Select a form</p>
            <Select aria-label="Paper size" value={paper} onChange={(e) => setPaper(e.target.value as "A4" | "Letter")} className="h-9 w-[110px] md:h-9">
              <option value="A4">A4</option>
              <option value="Letter">Letter</option>
            </Select>
          </div>
          <ul className="flex flex-col gap-1">
            {rows.map((r) => (
              <li key={r.key}>
                <button
                  type="button"
                  disabled={!r.available || busy !== null}
                  onClick={() => generate(r.key)}
                  className="flex w-full items-center gap-3 rounded-[var(--radius-ctl)] px-2 py-2 text-left text-[13.5px] hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <FileText className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{r.title}</span>
                    {!r.available && r.reason && <span className="block text-[12px] text-ink-3">{r.reason}</span>}
                  </span>
                  {busy === r.key ? <span className="text-[12px] text-ink-3">Creating…</span> : r.latest && r.available ? <RefreshCcw className="size-3.5 text-ink-3" strokeWidth={2} aria-label="New version" /> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {made.length === 0 ? (
        !open && <p className="px-4 py-3 text-[13px] text-ink-3 sm:px-5">{available.length} form{available.length === 1 ? "" : "s"} available. Select Create to generate a document.</p>
      ) : (
        <ul className="divide-y divide-line">
          {made.map((r) => {
            const d = r.latest!;
            return (
              <li key={d.id} className="px-4 py-3 sm:px-5">
                <div className="flex items-start gap-3">
                  <FileText className="mt-0.5 size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <a href={d.url} target="_blank" rel="noopener" className="block text-[13.5px] font-medium hover:underline">
                      {d.title}
                    </a>
                    <p className="tabular text-[12px] text-ink-3">
                      {d.control_number}
                      {d.version > 1 ? ` · v${d.version}` : ""} · {fmtDateTime(d.generated_at)}
                    </p>
                  </div>
                  <DocStatus s={d.status} />
                </div>
                {staff && !["voided", "superseded"].includes(d.status) && (
                  <div className="mt-2 flex flex-wrap gap-1.5 pl-7">
                    {(d.status === "approved" || d.status === "final") && (
                      <Button size="sm" variant="ghost" icon={Send} onClick={() => issue(d)}>
                        Issue
                      </Button>
                    )}
                    {d.status === "issued" && (
                      <Button size="sm" variant="ghost" icon={PenLine} onClick={() => setSigning(d)}>
                        Signed copy
                      </Button>
                    )}
                    {me?.role === "admin" && (
                      <Button size="sm" variant="ghost" icon={Ban} onClick={() => setVoiding(d)}>
                        Void
                      </Button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <SignedDialog doc={signing} onClose={() => setSigning(null)} onDone={q.reload} />
      <VoidDialog doc={voiding} onClose={() => setVoiding(null)} onDone={q.reload} />
    </Panel>
  );
}

function SignedDialog({ doc, onClose, onDone }: { doc: Doc | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!doc || !file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.set("file", file);
      await api(`/api/v1/documents/${doc.id}/signed`, { method: "POST", body: fd });
      toast("Signed copy recorded");
      onDone();
      onClose();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={Boolean(doc)}
      onClose={onClose}
      title="Record the signed copy"
      description="Upload the scan of the wet-signed document. It is kept as a signed copy; it is not treated as a verified electronic signature."
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" icon={Upload} busy={busy} disabled={!file} onClick={save}>
            Upload
          </Button>
        </>
      }
    >
      <Field label="Signed scan (PDF or image)" htmlFor="signed-file">
        <Input id="signed-file" type="file" accept=".pdf,.png,.jpg,.jpeg" className="pt-2" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
    </Dialog>
  );
}

function VoidDialog({ doc, onClose, onDone }: { doc: Doc | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!doc) return;
    setBusy(true);
    try {
      await post(`/api/v1/documents/${doc.id}/void`, { reason });
      toast(`Voided · ${doc.control_number}`);
      setReason("");
      onDone();
      onClose();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={Boolean(doc)}
      onClose={onClose}
      title={`Void ${doc?.control_number ?? ""}`}
      description="The document stays on record as void. Create a new version if it needs replacing."
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="danger" icon={Ban} busy={busy} disabled={!reason.trim()} onClick={save}>
            Void
          </Button>
        </>
      }
    >
      <Field label="Reason" required htmlFor="void-reason">
        <Textarea id="void-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Dialog>
  );
}

/** Register of every generated document (Reports › Documents). */
export function DocumentsRegister() {
  const [status, setStatus] = useState<string | undefined>();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const data = useApi<{ items: Doc[]; total: number }>(`/api/v1/documents${qs({ status, q: q.trim(), page, page_size: 50 })}`);
  return (
    <Panel>
      <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
        <Input type="search" placeholder="Search control number, form or record" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
        <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0">
          {[undefined, "approved", "final", "issued", "signed", "for_approval", "draft", "voided"].map((s) => (
            <Chip key={s ?? "all"} on={status === s} onClick={() => (setStatus(s), setPage(1))}>
              {s ? DOC_STATUS[s as Doc["status"]] : "Current"}
            </Chip>
          ))}
        </div>
      </div>
      {!data.data ? (
        <SkeletonRows />
      ) : data.data.items.length === 0 ? (
        <EmptyState icon={FileText} title="No documents yet" body="Create forms from a record's Documents panel, or a monthly report from the Reports tab." compact />
      ) : (
        <>
          <ul className="divide-y divide-line">
            {data.data.items.map((d) => (
              <li key={d.id}>
                <a href={d.url} target="_blank" rel="noopener" className="flex items-center gap-3 px-4 py-3 hover:bg-canvas sm:px-5">
                  <FileText className="size-[18px] shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-medium">{d.title}</span>
                    <span className="tabular block text-[12px] text-ink-3">
                      {d.control_number}
                      {d.version > 1 ? ` v${d.version}` : ""} · {d.related_ref ?? ""} · {d.generated_by.name} · {fmtDateTime(d.generated_at)}
                    </span>
                  </span>
                  <DocStatus s={d.status} />
                </a>
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={50} total={data.data.total} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

