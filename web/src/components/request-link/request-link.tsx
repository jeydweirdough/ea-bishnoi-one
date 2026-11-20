"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CircleCheck, Package, Plus, Search, Send, TriangleAlert, Trash2, type LucideIcon } from "lucide-react";
import { api, useApi, type ApiError } from "@/lib/api";
import { Mark } from "@/components/icons";
import { ActionRow, Button, Field, Input, Segmented, Select, Switch, Textarea } from "@/components/ui/controls";
import { PendingPhotos, shrink } from "@/components/ui/photos";
import { cn } from "@/lib/cn";

type Options = {
  companies: { id: number; code: string; name: string }[];
  departments: { id: number; name: string; company_id: number }[];
  concern_categories: string[];
  supply_categories: string[];
  units: string[];
  me: { name: string; email: string | null; company: string; company_id: number; department: string | null } | null;
  max_photos: number;
};
type Line = { item_name: string; quantity: string; unit: string };
type Sent = { reference: string; status: "received" | "submitted"; requests: { id: number; reference: string; status: string }[] };
type StatusOut = { reference: string; received_at: string; status: "new" | "accepted" | "declined"; status_label: string; decline_reason: string | null; requests: { reference: string; subject: string; status: string }[] };

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

/** The one link for everyone: report a problem, request items, or both. Works signed in or not. */
export function RequestLinkPage() {
  const [tab, setTab] = useState<"new" | "check">("new");
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="border-b border-line bg-rail">
        <div className="mx-auto flex h-[var(--topbar-h)] max-w-[680px] items-center gap-2.5 px-4 sm:px-6">
          <Mark size={28} />
          <span className="flex flex-col leading-none">
            <span className="text-[15px] font-bold tracking-[-0.01em]">Executive Admin</span>
            <span className="mt-1 text-[11.5px] font-medium text-ink-3">Bishnoi One · Corporate Services</span>
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-[680px] px-4 pb-16 pt-7 sm:px-6 sm:pt-10">
        <h1 className="text-[28px] font-bold leading-tight tracking-[-0.02em] sm:text-[32px]">Requests & reports</h1>
        <p className="mt-1.5 max-w-[52ch] text-[15px] leading-relaxed text-ink-2">Report a problem, ask for items, or both in one go. The EA team gets it right away.</p>
        <Segmented
          className="mt-5"
          label="What do you want to do"
          value={tab}
          onChange={setTab}
          options={[
            { value: "new", label: "New request", icon: Send },
            { value: "check", label: "Check a request", icon: Search },
          ]}
        />
        <div className="mt-6">{tab === "new" ? <NewRequest onCheck={() => setTab("check")} /> : <CheckStatus />}</div>
      </main>
    </div>
  );
}

function Section({ n, title, lead, children }: { n: number; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[var(--radius-panel)] border border-line bg-sheet p-4 sm:p-6" aria-labelledby={`s-${n}`}>
      <h2 id={`s-${n}`} className="flex items-baseline gap-2.5 text-[17px] font-bold tracking-[-0.01em]">
        <span className="tabular text-[13px] font-medium text-ink-3">{n}</span>
        {title}
      </h2>
      {lead && <p className="mt-1 text-[13.5px] leading-relaxed text-ink-3">{lead}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function NeedCard({ on, onClick, icon: Icon, title, body }: { on: boolean; onClick: () => void; icon: LucideIcon; title: string; body: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "flex min-h-[88px] w-full items-start gap-3 rounded-[var(--radius-ctl)] border p-3.5 text-left transition-colors duration-150",
        on ? "border-ink bg-ink text-white" : "border-edge bg-sheet hover:border-mute",
      )}
    >
      <Icon className="mt-0.5 size-5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0">
        <span className="block text-[15px] font-bold">{title}</span>
        <span className={cn("mt-0.5 block text-[13px] leading-snug", on ? "text-white/75" : "text-ink-3")}>{body}</span>
      </span>
      <span aria-hidden="true" className={cn("ml-auto mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border", on ? "border-white bg-white text-ink" : "border-edge")}>
        {on && <CircleCheck className="size-5" strokeWidth={2} />}
      </span>
    </button>
  );
}

function NewRequest({ onCheck }: { onCheck: () => void }) {
  const o = useApi<Options>("/api/v1/public/request-form");
  const me = o.data?.me ?? null;
  const [who, setWho] = useState({ name: "", email: "", phone: "", position: "", company_id: "", department_id: "" });
  const [wantProblem, setWantProblem] = useState(false);
  const [wantItems, setWantItems] = useState(false);
  const [problem, setProblem] = useState({ category: "", subject: "", description: "", location: "", related_item: "" });
  const [lines, setLines] = useState<Line[]>([{ item_name: "", quantity: "1", unit: "pc" }]);
  const [supplies, setSupplies] = useState({ category: "Office supplies", purpose: "", needed_by: "", delivery_location: "" });
  const [urgent, setUrgent] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const [website, setWebsite] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);

  const companyId = who.company_id || (o.data?.companies.length === 1 ? String(o.data.companies[0].id) : "");
  const depts = useMemo(() => (o.data?.departments ?? []).filter((d) => String(d.company_id) === companyId), [o.data, companyId]);
  const e = (k: string) => errors[k];

  function reset() {
    setSent(null);
    setWantProblem(false);
    setWantItems(false);
    setProblem({ category: "", subject: "", description: "", location: "", related_item: "" });
    setLines([{ item_name: "", quantity: "1", unit: "pc" }]);
    setSupplies({ category: "Office supplies", purpose: "", needed_by: "", delivery_location: "" });
    setUrgent(false);
    setPhotos([]);
    setErrors({});
    setMessage(undefined);
  }

  async function send() {
    setBusy(true);
    setErrors({});
    setMessage(undefined);
    const body = {
      ...(me ? {} : { ...who, company_id: companyId ? Number(companyId) : null, department_id: who.department_id ? Number(who.department_id) : null }),
      problem: wantProblem ? { ...problem, location: problem.location || null, related_item: problem.related_item || null } : null,
      supplies: wantItems
        ? { ...supplies, delivery_location: supplies.delivery_location || null, needed_by: supplies.needed_by || undefined, items: lines.filter((l) => l.item_name.trim()).map((l) => ({ ...l, quantity: Number(l.quantity) || 0 })) }
        : null,
      urgent,
      website,
    };
    const fd = new FormData();
    fd.set("data", JSON.stringify(body));
    for (const f of photos) fd.append("photos", await shrink(f));
    try {
      setSent(await api<Sent>("/api/v1/public/requests", { method: "POST", body: fd }));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      const x = err as ApiError;
      setErrors(x.fields ?? {});
      setMessage(x.message);
    } finally {
      setBusy(false);
    }
  }

  if (o.error) return <p className="text-[14px] text-danger">{o.error.message}</p>;
  if (!o.data) return <div className="h-64 animate-pulse rounded-[var(--radius-panel)] bg-sheet" />;
  if (sent) return <SentCard sent={sent} onAnother={reset} onCheck={onCheck} />;

  const itemErr = Object.entries(errors).find(([k]) => k.startsWith("supplies.items"))?.[1];
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(ev) => {
        ev.preventDefault();
        send();
      }}
      noValidate
    >
      <Section n={1} title="About you" lead={me ? undefined : "So we know who it's from and how to reach you."}>
        {me ? (
          <p className="rounded-[var(--radius-ctl)] border border-line bg-canvas px-3.5 py-3 text-[14px]">
            Sending as <span className="font-bold">{me.name}</span>
            <span className="block text-[13px] text-ink-3">{[me.company, me.department].filter(Boolean).join(" · ")}</span>
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" required htmlFor="w-name" error={e("name")} className="sm:col-span-2">
              <Input id="w-name" autoComplete="name" value={who.name} onChange={(ev) => setWho({ ...who, name: ev.target.value })} invalid={!!e("name")} />
            </Field>
            <Field label="Work email" required htmlFor="w-email" error={e("email")} hint="We'll use it to match you and for status checks.">
              <Input id="w-email" type="email" autoComplete="email" inputMode="email" value={who.email} onChange={(ev) => setWho({ ...who, email: ev.target.value })} invalid={!!e("email")} />
            </Field>
            <Field label="Mobile number" htmlFor="w-phone" error={e("phone")}>
              <Input id="w-phone" type="tel" autoComplete="tel" inputMode="tel" value={who.phone} onChange={(ev) => setWho({ ...who, phone: ev.target.value })} />
            </Field>
            <Field label="Company" required htmlFor="w-company" error={e("company_id")}>
              <Select id="w-company" value={companyId} onChange={(ev) => setWho({ ...who, company_id: ev.target.value, department_id: "" })} invalid={!!e("company_id")}>
                {!companyId && <option value="">Choose…</option>}
                {o.data.companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Department" htmlFor="w-dept" error={e("department_id")}>
              <Select id="w-dept" value={who.department_id} onChange={(ev) => setWho({ ...who, department_id: ev.target.value })} disabled={!companyId}>
                <option value="">—</option>
                {depts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Position" htmlFor="w-position" className="sm:col-span-2">
              <Input id="w-position" autoComplete="organization-title" value={who.position} onChange={(ev) => setWho({ ...who, position: ev.target.value })} />
            </Field>
          </div>
        )}
      </Section>

      <Section n={2} title="What do you need?" lead="Choose one or both.">
        <div className="grid gap-2.5 sm:grid-cols-2">
          <NeedCard on={wantProblem} onClick={() => setWantProblem(!wantProblem)} icon={TriangleAlert} title="Report a problem" body="Something broken, unsafe or not working." />
          <NeedCard on={wantItems} onClick={() => setWantItems(!wantItems)} icon={Package} title="Request items" body="Supplies, equipment or things to buy." />
        </div>
        {e("need") && (
          <p role="alert" className="mt-2 text-[13px] text-danger">
            {e("need")}
          </p>
        )}
      </Section>

      {wantProblem && (
        <Section n={3} title="The problem">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Type" required htmlFor="p-cat" error={e("problem.category")}>
              <Select id="p-cat" value={problem.category} onChange={(ev) => setProblem({ ...problem, category: ev.target.value })} invalid={!!e("problem.category")}>
                {!problem.category && <option value="">Choose…</option>}
                {o.data.concern_categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
            <Field label="Where" htmlFor="p-loc" error={e("problem.location")}>
              <Input id="p-loc" placeholder="Branch, floor or room" value={problem.location} onChange={(ev) => setProblem({ ...problem, location: ev.target.value })} />
            </Field>
            <Field label="What's wrong" required htmlFor="p-subj" error={e("problem.subject")} className="sm:col-span-2">
              <Input id="p-subj" placeholder="e.g. Aircon leaking in the pantry" value={problem.subject} onChange={(ev) => setProblem({ ...problem, subject: ev.target.value })} invalid={!!e("problem.subject")} />
            </Field>
            <Field label="Details" required htmlFor="p-desc" error={e("problem.description")} className="sm:col-span-2">
              <Textarea id="p-desc" rows={3} placeholder="What happened, since when, and what's affected" value={problem.description} onChange={(ev) => setProblem({ ...problem, description: ev.target.value })} invalid={!!e("problem.description")} />
            </Field>
            <Field label="Item involved" htmlFor="p-item" hint="Optional. Its name or serial number if you know it." className="sm:col-span-2">
              <Input id="p-item" value={problem.related_item} onChange={(ev) => setProblem({ ...problem, related_item: ev.target.value })} />
            </Field>
          </div>
        </Section>
      )}

      {wantItems && (
        <Section n={wantProblem ? 4 : 3} title="The items">
          <ul className="flex flex-col gap-2.5">
            {lines.map((l, i) => (
              <li key={i} className="grid grid-cols-2 gap-2 rounded-[var(--radius-ctl)] border border-line p-2.5 sm:grid-cols-[minmax(0,1fr)_84px_110px_40px] sm:items-end sm:border-0 sm:p-0">
                <Field label={i === 0 ? "Item" : `Item ${i + 1}`} required htmlFor={`i-name-${i}`} error={e(`supplies.items.${i}.item_name`)} className="col-span-2 sm:col-span-1">
                  <Input id={`i-name-${i}`} placeholder="e.g. Bond paper A4" value={l.item_name} onChange={(ev) => setLines(lines.map((x, j) => (j === i ? { ...x, item_name: ev.target.value } : x)))} />
                </Field>
                <Field label="Qty" required htmlFor={`i-qty-${i}`} error={e(`supplies.items.${i}.quantity`)}>
                  <Input id={`i-qty-${i}`} inputMode="numeric" className="tabular" value={l.quantity} onChange={(ev) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: ev.target.value.replace(/[^0-9]/g, "") } : x)))} />
                </Field>
                <Field label="Unit" htmlFor={`i-unit-${i}`}>
                  <Select id={`i-unit-${i}`} value={l.unit} onChange={(ev) => setLines(lines.map((x, j) => (j === i ? { ...x, unit: ev.target.value } : x)))}>
                    {o.data!.units.map((u) => (
                      <option key={u}>{u}</option>
                    ))}
                  </Select>
                </Field>
                <span className="col-span-2 flex justify-end sm:col-span-1">
                  {lines.length > 1 && (
                    <button type="button" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label={`Remove item ${i + 1}`} className="flex size-10 items-center justify-center rounded-[var(--radius-ctl)] text-ink-3 hover:bg-hover hover:text-ink">
                      <Trash2 className="size-4" strokeWidth={1.75} />
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
          {itemErr && <p className="mt-2 text-[13px] text-danger">{itemErr}</p>}
          {lines.length < 30 && (
            <Button size="sm" variant="ghost" icon={Plus} className="mt-2" onClick={() => setLines([...lines, { item_name: "", quantity: "1", unit: "pc" }])}>
              Add another item
            </Button>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Kind of items" htmlFor="s-cat">
              <Select id="s-cat" value={supplies.category} onChange={(ev) => setSupplies({ ...supplies, category: ev.target.value })}>
                {o.data.supply_categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
            <Field label="Needed by" required htmlFor="s-date" error={e("supplies.needed_by")}>
              <Input id="s-date" type="date" min={today()} value={supplies.needed_by} onChange={(ev) => setSupplies({ ...supplies, needed_by: ev.target.value })} invalid={!!e("supplies.needed_by")} />
            </Field>
            <Field label="What it's for" required htmlFor="s-purpose" error={e("supplies.purpose")} className="sm:col-span-2">
              <Input id="s-purpose" placeholder="e.g. Daily receipts at the front desk" value={supplies.purpose} onChange={(ev) => setSupplies({ ...supplies, purpose: ev.target.value })} invalid={!!e("supplies.purpose")} />
            </Field>
            <Field label="Deliver to" htmlFor="s-deliver" className="sm:col-span-2">
              <Input id="s-deliver" placeholder="Branch, floor or desk" value={supplies.delivery_location} onChange={(ev) => setSupplies({ ...supplies, delivery_location: ev.target.value })} />
            </Field>
          </div>
        </Section>
      )}

      {(wantProblem || wantItems) && (
        <section className="flex flex-col gap-4 rounded-[var(--radius-panel)] border border-line bg-sheet p-4 sm:p-6" aria-label="Photos and urgency">
          <PendingPhotos files={photos} onChange={setPhotos} max={o.data.max_photos} note={wantProblem ? "show us the problem" : "show the exact item"} />
          {e("photos") && <p className="-mt-3 text-[13px] text-danger">{e("photos")}</p>}
          <Switch checked={urgent} onChange={setUrgent} label="This is urgent" hint="For safety issues, or when work has stopped." />
        </section>
      )}

      {/* Left empty by people. Bots that fill every field are quietly ignored. */}
      <div aria-hidden="true" className="absolute left-[-9999px] h-px w-px overflow-hidden">
        <label htmlFor="w-website">Website</label>
        <input id="w-website" tabIndex={-1} autoComplete="off" value={website} onChange={(ev) => setWebsite(ev.target.value)} />
      </div>

      {message && (
        <p role="alert" className="text-[13.5px] text-danger">
          {message}
        </p>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[12.5px] leading-relaxed text-ink-3">Your details are used only to handle this request.</p>
        <Button type="submit" variant="primary" icon={Send} busy={busy} disabled={!wantProblem && !wantItems} className="w-full sm:w-auto">
          Send request
        </Button>
      </div>
    </form>
  );
}

function SentCard({ sent, onAnother, onCheck }: { sent: Sent; onAnother: () => void; onCheck: () => void }) {
  const direct = sent.status === "submitted";
  return (
    <div className="rounded-[var(--radius-panel)] border border-line bg-sheet p-5 sm:p-7" role="status">
      <CircleCheck className="size-8" strokeWidth={1.6} aria-hidden="true" />
      <h2 className="mt-3 text-[22px] font-bold tracking-[-0.01em]">{direct ? "Sent for approval" : "Request received"}</h2>
      <p className="mt-1 text-[14.5px] leading-relaxed text-ink-2">
        {direct ? "It's on its way through the usual approval route. You'll get updates in the app." : "The EA team will check it and send it for approval. Keep this reference to check progress."}
      </p>
      {!direct && <p className="tabular mt-4 text-[28px] font-bold tracking-[-0.01em]">{sent.reference}</p>}
      {direct && (
        <ul className="mt-4 divide-y divide-line rounded-[var(--radius-ctl)] border border-line">
          {sent.requests.map((r) => (
            <li key={r.id}>
              <Link href={`/r/${r.id}`} className="flex items-center justify-between px-3.5 py-3 text-[14px] hover:bg-canvas">
                <span className="tabular font-bold">{r.reference}</span>
                <span className="text-ink-3">{r.status}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <ActionRow className="mt-6">
        <Button variant="primary" icon={Plus} onClick={onAnother}>
          Send another
        </Button>
        {!direct && (
          <Button icon={Search} onClick={onCheck}>
            Check status
          </Button>
        )}
      </ActionRow>
    </div>
  );
}

function CheckStatus() {
  const [ref, setRef] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<StatusOut | null>(null);
  const [error, setError] = useState<string>();
  async function check() {
    setBusy(true);
    setError(undefined);
    setOut(null);
    try {
      setOut(await api<StatusOut>(`/api/v1/public/requests/status?reference=${encodeURIComponent(ref.trim())}&email=${encodeURIComponent(email.trim())}`));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <form
        className="grid gap-4 rounded-[var(--radius-panel)] border border-line bg-sheet p-4 sm:grid-cols-2 sm:p-6"
        onSubmit={(ev) => {
          ev.preventDefault();
          check();
        }}
      >
        <Field label="Reference" htmlFor="c-ref" hint="Starts with EA-WEB-">
          <Input id="c-ref" className="tabular uppercase" value={ref} onChange={(ev) => setRef(ev.target.value)} autoComplete="off" />
        </Field>
        <Field label="Email you used" htmlFor="c-email">
          <Input id="c-email" type="email" inputMode="email" autoComplete="email" value={email} onChange={(ev) => setEmail(ev.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Button type="submit" variant="primary" icon={Search} busy={busy} disabled={!ref.trim() || !email.trim()} className="w-full sm:w-auto">
            Check
          </Button>
        </div>
      </form>
      {error && (
        <p role="alert" className="text-[13.5px] text-danger">
          {error}
        </p>
      )}
      {out && (
        <div className="rounded-[var(--radius-panel)] border border-line bg-sheet p-4 sm:p-6" role="status">
          <p className="tabular text-[13px] font-medium text-ink-3">{out.reference}</p>
          <p className="mt-1 text-[18px] font-bold">{out.status_label}</p>
          {out.decline_reason && <p className="mt-1 text-[14px] text-ink-2">Reason: {out.decline_reason}</p>}
          {out.requests.length > 0 && (
            <ul className="mt-4 divide-y divide-line rounded-[var(--radius-ctl)] border border-line">
              {out.requests.map((r) => (
                <li key={r.reference} className="flex items-start justify-between gap-3 px-3.5 py-3 text-[14px]">
                  <span className="min-w-0">
                    <span className="tabular block font-bold">{r.reference}</span>
                    <span className="block truncate text-[13px] text-ink-3">{r.subject}</span>
                  </span>
                  <span className="shrink-0 text-right font-medium">{r.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
