"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Inbox, Package, TriangleAlert, UserPlus, X } from "lucide-react";
import { api, fmtDateTime, invalidate, qs, useApi, type ApiError } from "@/lib/api";
import { ModuleShell } from "@/components/ops/module-shell";
import { Button, Chip, Field, Textarea } from "@/components/ui/controls";
import { Dialog, EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { PeoplePicker } from "@/components/requests/people-picker";
import { cn } from "@/lib/cn";

type Person = { id: number; name: string } | null;
type WebReq = {
  id: number;
  reference: string;
  name: string;
  email: string;
  phone: string | null;
  position: string | null;
  company: { id: number; code: string; name: string };
  department: { id: number; name: string } | null;
  problem: { category: string; subject: string; description: string; location: string | null; related_item: string | null } | null;
  supplies: { category: string; items: { item_name: string; quantity: number; unit: string }[]; purpose: string; needed_by: string; delivery_location: string | null } | null;
  urgent: boolean;
  photos: string[];
  status: "new" | "accepted" | "declined";
  match: Person;
  requests: { id: number; reference: string; subject: string; status: string }[];
  handled_by: Person;
  handled_at: string | null;
  decline_reason: string | null;
  created_at: string;
  version: number;
};

const VIEWS = [
  { value: "new", label: "Waiting" },
  { value: "accepted", label: "Accepted" },
  { value: "declined", label: "Declined" },
  { value: "all", label: "All" },
] as const;

function what(w: WebReq) {
  return [w.problem && `Problem: ${w.problem.subject}`, w.supplies && `${w.supplies.items.length} item${w.supplies.items.length === 1 ? "" : "s"}`].filter(Boolean).join(" · ");
}

/** EA inbox for the shared request link: confirm who sent it, then accept (files the real requests) or decline. */
export function FromLinkPage() {
  const toast = useToast();
  const [view, setView] = useState<(typeof VIEWS)[number]["value"]>("new");
  const [open, setOpen] = useState<number | null>(null);
  const data = useApi<{ items: WebReq[]; waiting: number }>(`/api/v1/web-requests${qs({ status: view })}`);
  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get("id"));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- open the one a notification points to
    if (id) setOpen(id);
  }, []);
  async function copy() {
    const link = `${window.location.origin}/request`;
    try {
      await navigator.clipboard.writeText(link);
      toast(`Copied · ${link}`);
    } catch {
      toast(link);
    }
  }
  return (
    <ModuleShell
      group="requests"
      item="from-link"
      actions={
        <>
          <Button variant="primary" icon={Copy} onClick={copy}>
            Copy request link
          </Button>
          <Link href="/request" target="_blank" rel="noopener" className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-ctl)] border border-edge bg-sheet px-4 text-[14px] font-medium hover:border-mute md:h-10">
            <ExternalLink className="size-4" strokeWidth={1.75} aria-hidden="true" />
            Open the form
          </Link>
        </>
      }
    >
      <Panel>
        <div className="no-scrollbar flex gap-1.5 overflow-x-auto border-b border-line p-3 sm:px-5">
          {VIEWS.map((v) => (
            <Chip key={v.value} on={view === v.value} onClick={() => setView(v.value)} count={v.value === "new" ? data.data?.waiting : undefined}>
              {v.label}
            </Chip>
          ))}
        </div>
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title={view === "new" ? "Nothing waiting" : "Nothing here"}
            body={view === "new" ? "Requests sent through the request link appear here for you to check. Share the link with Copy request link." : undefined}
            compact
          />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((w) => (
              <li key={w.id}>
                <button type="button" onClick={() => setOpen(w.id)} className="flex w-full items-start gap-3.5 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-canvas sm:items-center sm:px-5">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line bg-canvas" aria-hidden="true">
                    {w.problem ? <TriangleAlert className="size-[18px]" strokeWidth={1.75} /> : <Package className="size-[18px]" strokeWidth={1.75} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[15px] font-bold">{w.name}</span>
                      {w.urgent && <span className="shrink-0 rounded-full bg-danger-soft px-2 py-0.5 text-[11.5px] font-bold text-danger">Urgent</span>}
                    </span>
                    <span className="mt-0.5 block truncate text-[13px] text-ink-2">{what(w)}</span>
                    <span className="mt-0.5 block text-[12.5px] text-ink-3">
                      <span className="tabular">{w.reference}</span> · {[w.company.code, w.department?.name].filter(Boolean).join(" · ")} · {fmtDateTime(w.created_at)}
                    </span>
                  </span>
                  <span className="hidden shrink-0 text-right text-[12.5px] sm:block">
                    {w.status === "new" ? (w.match ? <span className="text-ink-2">Matches {w.match.name}</span> : <span className="text-ink-3">Not in the directory</span>) : <span className="font-medium">{w.status === "accepted" ? "Accepted" : "Declined"}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <WebRequestDialog id={open} onClose={() => setOpen(null)} onChanged={() => (data.reload(), invalidate())} />
    </ModuleShell>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  if (!v) return null;
  return (
    <div className="flex justify-between gap-4 py-2 text-[13.5px]">
      <dt className="shrink-0 text-ink-3">{k}</dt>
      <dd className="min-w-0 text-right font-medium [overflow-wrap:anywhere]">{v}</dd>
    </div>
  );
}

function WebRequestDialog({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const q = useApi<WebReq>(id ? `/api/v1/web-requests/${id}` : null);
  const w = id && q.data?.id === id ? q.data : undefined;
  const [who, setWho] = useState<number | null>(null);
  const [addNew, setAddNew] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [seen, setSeen] = useState<number | null>(null);
  if (w && seen !== w.id) {
    setSeen(w.id);
    setWho(w.match?.id ?? null);
    setAddNew(!w.match);
    setDeclining(false);
    setReason("");
    setError(undefined);
  }

  async function act(path: "accept" | "decline") {
    if (!w) return;
    setBusy(true);
    setError(undefined);
    try {
      const body = path === "accept" ? (addNew ? { add_person: true, version: w.version } : { employee_id: who, version: w.version }) : { reason, version: w.version };
      const res = await api<WebReq>(`/api/v1/web-requests/${w.id}/${path}`, { method: "POST", json: body });
      q.setData(res);
      toast(path === "accept" ? `Accepted · ${res.requests.map((r) => r.reference).join(", ")}` : `Declined · ${res.reference}`);
      onChanged();
      if (path === "decline") onClose();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const pending = w?.status === "new";
  return (
    <Dialog
      open={id !== null}
      onClose={onClose}
      wide
      title={w ? `${w.name} · ${w.reference}` : "Loading…"}
      description={w ? `Sent ${fmtDateTime(w.created_at)} through the request link` : undefined}
      footer={
        pending ? (
          declining ? (
            <>
              <Button onClick={() => setDeclining(false)}>Back</Button>
              <Button variant="danger" icon={X} busy={busy} disabled={!reason.trim()} onClick={() => act("decline")}>
                Decline
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" icon={X} onClick={() => setDeclining(true)}>
                Decline
              </Button>
              <Button variant="primary" icon={Check} busy={busy} disabled={!addNew && !who} onClick={() => act("accept")}>
                Accept and send for approval
              </Button>
            </>
          )
        ) : (
          <Button onClick={onClose}>Close</Button>
        )
      }
    >
      {q.error ? (
        <ErrorState message={q.error.message} />
      ) : !w ? (
        <SkeletonRows rows={3} />
      ) : (
        <div className="flex flex-col gap-5">
          <dl className="divide-y divide-line rounded-[var(--radius-ctl)] border border-line px-3.5">
            <Row k="Email" v={<a href={`mailto:${w.email}`} className="hover:underline">{w.email}</a>} />
            <Row k="Mobile" v={w.phone && <a href={`tel:${w.phone}`} className="hover:underline">{w.phone}</a>} />
            <Row k="Position" v={w.position} />
            <Row k="Company" v={w.company.name} />
            <Row k="Department" v={w.department?.name} />
            <Row k="Urgent" v={w.urgent ? "Yes" : null} />
          </dl>
          {w.problem && (
            <section>
              <h3 className="flex items-center gap-2 text-[14.5px] font-bold">
                <TriangleAlert className="size-4" strokeWidth={1.75} aria-hidden="true" />
                Problem · {w.problem.category}
              </h3>
              <p className="mt-1.5 text-[14.5px] font-medium">{w.problem.subject}</p>
              <p className="mt-1 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{w.problem.description}</p>
              {(w.problem.location || w.problem.related_item) && (
                <p className="mt-1 text-[12.5px] text-ink-3">{[w.problem.location && `Where: ${w.problem.location}`, w.problem.related_item && `Item: ${w.problem.related_item}`].filter(Boolean).join(" · ")}</p>
              )}
            </section>
          )}
          {w.supplies && (
            <section>
              <h3 className="flex items-center gap-2 text-[14.5px] font-bold">
                <Package className="size-4" strokeWidth={1.75} aria-hidden="true" />
                Items · {w.supplies.category}
              </h3>
              <ul className="mt-1.5 divide-y divide-line rounded-[var(--radius-ctl)] border border-line">
                {w.supplies.items.map((it, i) => (
                  <li key={i} className="flex justify-between gap-3 px-3.5 py-2 text-[13.5px]">
                    <span>{it.item_name}</span>
                    <span className="tabular shrink-0 font-medium">
                      {it.quantity} {it.unit}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-[12.5px] text-ink-3">
                For: {w.supplies.purpose} · Needed by {w.supplies.needed_by}
                {w.supplies.delivery_location ? ` · Deliver to ${w.supplies.delivery_location}` : ""}
              </p>
            </section>
          )}
          {w.photos.length > 0 && (
            <ul className="no-scrollbar flex gap-2 overflow-x-auto">
              {w.photos.map((src, i) => (
                <li key={src} className="shrink-0">
                  <a href={src} target="_blank" rel="noopener">
                    {/* eslint-disable-next-line @next/next/no-img-element -- private, served by the API */}
                    <img src={src} alt={`Photo ${i + 1}`} className="size-24 rounded-[8px] border border-line object-cover" />
                  </a>
                </li>
              ))}
            </ul>
          )}

          {pending && !declining && (
            <section className="rounded-[var(--radius-ctl)] border border-line bg-canvas p-3.5">
              <h3 className="text-[14px] font-bold">Who sent it?</h3>
              <p className="mt-0.5 text-[12.5px] leading-snug text-ink-3">
                {w.match ? `The email matches ${w.match.name}. Change it if that's wrong.` : "The email isn't in the directory. Pick the person, or add them as a new person."} The requests are filed under them and follow the usual approval route.
              </p>
              <div className="mt-3 flex flex-col gap-2">
                <label className={cn("flex items-center gap-2.5 text-[13.5px]", addNew && "text-ink-3")}>
                  <input type="radio" name="who" checked={!addNew} onChange={() => setAddNew(false)} className="size-4 accent-[#111]" />
                  Someone in the directory
                </label>
                {!addNew && <PeoplePicker id="wr-who" value={who} onChange={setWho} placeholder="Choose the person" />}
                <label className={cn("flex items-center gap-2.5 text-[13.5px]", !addNew && "text-ink-3")}>
                  <input type="radio" name="who" checked={addNew} onChange={() => setAddNew(true)} className="size-4 accent-[#111]" />
                  <UserPlus className="size-4" strokeWidth={1.75} aria-hidden="true" />
                  Add {w.name} as a new person
                </label>
              </div>
            </section>
          )}
          {pending && declining && (
            <Field label="Why is it declined?" required htmlFor="wr-reason" hint="The sender sees this when they check the status.">
              <Textarea id="wr-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Sent twice; already handled under EA-REQ-…" />
            </Field>
          )}
          {!pending && (
            <section className="rounded-[var(--radius-ctl)] border border-line p-3.5 text-[13.5px]">
              <p className="font-bold">
                {w.status === "accepted" ? "Accepted" : "Declined"} by {w.handled_by?.name} · {fmtDateTime(w.handled_at)}
              </p>
              {w.decline_reason && <p className="mt-1 text-ink-2">{w.decline_reason}</p>}
              {w.requests.length > 0 && (
                <ul className="mt-2 flex flex-col gap-1">
                  {w.requests.map((r) => (
                    <li key={r.id}>
                      <Link href={`/r/${r.id}`} className="font-medium hover:underline">
                        <span className="tabular">{r.reference}</span> · {r.subject}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {error && (
            <p role="alert" className="text-[13.5px] text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}
