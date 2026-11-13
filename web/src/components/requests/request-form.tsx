"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  ChevronDown,
  CircleHelp,
  Flag,
  Hammer,
  Monitor,
  MonitorX,
  Package,
  Paperclip,
  Camera,
  Plus,
  Send,
  ShieldAlert,
  ShoppingCart,
  Store,
  Trash2,
  Users,
  Wrench,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { api, invalidate, post, useApi, ApiError, fmtSize, type Kind, type Options, type Priority, type RequestDetail } from "@/lib/api";
import { Button, Field, Input, Segmented, Select, Textarea } from "@/components/ui/controls";
import { useToast } from "@/components/ui/feedback";
import { shrink } from "@/components/ui/photos";
import { cn } from "@/lib/cn";

type ItemDraft = {
  key: string;
  item_name: string;
  item_category: string;
  description: string;
  brand: string;
  model: string;
  quantity: string;
  unit: string;
  open: boolean;
};

const newItem = (): ItemDraft => ({
  key: Math.random().toString(36).slice(2),
  item_name: "",
  item_category: "",
  description: "",
  brand: "",
  model: "",
  quantity: "1",
  unit: "pc",
  open: false,
});

const PRIORITIES: { value: Priority; label: string; icon?: typeof Flag }[] = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High", icon: Flag },
  { value: "critical", label: "Urgent", icon: Flag },
];

/** Picture-first categories: one tap instead of reading a dropdown. */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  Facilities: Building2,
  "Damaged equipment": MonitorX,
  Repairs: Wrench,
  Maintenance: Hammer,
  "IT & equipment": Monitor,
  Utilities: Zap,
  "Safety & security": ShieldAlert,
  "Department concern": Users,
  Other: CircleHelp,
};

function newToken() {
  // randomUUID needs a secure context; phones on a LAN address over http fall back.
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.heic,.docx,.xlsx,.csv,.txt";
const MAX_MB = 10;

/** Quiet section heading: forms read as one sheet, not a stack of cards. */
function Step({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("flex flex-col gap-4", className)}>
      <h2 className="text-[16px] font-bold">{title}</h2>
      {children}
    </section>
  );
}

export function RequestForm({ mode, initial }: { mode: "concern" | "supplies"; initial?: RequestDetail }) {
  const router = useRouter();
  const toast = useToast();
  const options = useApi<Options>("/api/v1/requests/options");
  // Idempotency token: a retried save never creates a second request.
  const [token] = useState(newToken);

  const [id, setId] = useState<number | undefined>(initial?.id);
  const [version, setVersion] = useState<number | undefined>(initial?.version);
  const [kind, setKind] = useState<Kind>(initial ? (initial.kind === "repair" ? "concern" : initial.kind) : mode === "concern" ? "concern" : "supplies");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [relatedAsset, setRelatedAsset] = useState(initial?.related_asset ?? "");
  const [priority, setPriority] = useState<Priority>(initial?.requested_priority ?? "normal");
  const [neededBy, setNeededBy] = useState(initial?.needed_by ?? "");
  const [purpose, setPurpose] = useState(initial?.purpose ?? "");
  const [delivery, setDelivery] = useState(initial?.delivery_location ?? "");
  const [items, setItems] = useState<ItemDraft[]>(
    initial?.items.length
      ? initial.items.map((i) => ({
          key: String(i.id),
          item_name: i.item_name,
          item_category: i.item_category ?? "",
          description: i.description ?? "",
          brand: i.brand ?? "",
          model: i.model ?? "",
          quantity: String(i.quantity),
          unit: i.unit,
          open: Boolean(i.brand || i.model || i.description || i.item_category),
        }))
      : [newItem()],
  );
  const [files, setFiles] = useState<File[]>([]);
  const [existing, setExisting] = useState(initial?.attachments ?? []);
  const [reply, setReply] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);

  const isItems = mode === "supplies";
  const returned = initial?.status === "returned";
  const returnStep = initial?.steps.find((s) => s.status === "returned");
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const opts = options.data;

  // Optional fields live behind "More options"; open it if any already hold a value.
  const [more, setMore] = useState(
    Boolean(initial && (initial.related_asset || initial.delivery_location || initial.requested_priority !== "normal" || (!isItems && initial.needed_by) || (isItems && initial.description))),
  );

  const named = items.filter((i) => i.item_name.trim());
  // Item requests don't need a title: it is written from the items unless the person sets one.
  const autoTitle = named.length ? `${named[0].item_name.trim()}${named.length > 1 ? ` + ${named.length - 1} more` : ""}` : "";

  const payload = () => ({
    kind,
    category: isItems ? null : category || null,
    subject: (subject.trim() || (isItems ? autoTitle : "")).slice(0, 300),
    description: description.trim(),
    location: location || null,
    related_asset: relatedAsset || null,
    purpose: isItems ? purpose || null : null,
    delivery_location: isItems ? delivery || null : null,
    requested_priority: priority,
    needed_by: neededBy || null,
    items: isItems
      ? items
          .filter((i) => i.item_name.trim() || i.quantity !== "1" || i.brand || i.model)
          .map((i) => ({
            item_name: i.item_name.trim(),
            item_category: i.item_category || null,
            description: i.description || null,
            brand: i.brand || null,
            model: i.model || null,
            quantity: Number.parseInt(i.quantity, 10) || 0,
            unit: i.unit,
          }))
      : [],
    submit: false,
  });

  function addFiles(list: FileList | File[] | null) {
    if (!list) return;
    const next: File[] = [];
    for (const f of Array.from(list)) {
      if (f.size > MAX_MB * 1024 * 1024) {
        toast(`${f.name} is larger than ${MAX_MB} MB`, "error");
        continue;
      }
      next.push(f);
    }
    setFiles((cur) => [...cur, ...next].slice(0, 10 - existing.length));
  }

  async function save(submit: boolean) {
    setBusy(submit ? "submit" : "draft");
    setErrors({});
    setFormError(undefined);
    try {
      let detail: RequestDetail;
      if (id === undefined) {
        detail = await post<RequestDetail>("/api/v1/requests", { ...payload(), client_token: token });
      } else {
        detail = await api<RequestDetail>(`/api/v1/requests/${id}`, { method: "PATCH", json: { ...payload(), version } });
      }
      setId(detail.id);
      setVersion(detail.version);
      // Upload evidence before submitting so approvers see it from the start.
      const failed: string[] = [];
      for (const f of files) {
        const fd = new FormData();
        fd.set("owner_type", "request");
        fd.set("owner_id", String(detail.id));
        fd.set("purpose", "evidence");
        fd.set("file", f);
        try {
          await api("/api/v1/attachments", { method: "POST", body: fd });
        } catch (e) {
          failed.push(`${f.name}: ${(e as ApiError).message}`);
        }
      }
      setFiles([]);
      if (failed.length) {
        setFormError(`Saved, but ${failed.length === 1 ? "one file" : "some files"} could not be attached — ${failed.join("; ")}`);
        setBusy(null);
        return;
      }
      if (submit) {
        detail =
          detail.status === "returned"
            ? await post<RequestDetail>(`/api/v1/requests/${detail.id}/actions/resubmit`, { message: reply })
            : await post<RequestDetail>(`/api/v1/requests/${detail.id}/actions/submit`);
        toast(returned ? `Sent again · ${detail.reference}` : `Sent · ${detail.reference}`);
      } else {
        toast(`Saved as draft · ${detail.reference}`);
      }
      invalidate();
      router.push(`/r/${detail.id}`);
    } catch (e) {
      const err = e as ApiError;
      const fields = { ...(err.fields ?? {}) };
      // Item requests have no visible title field by default; point the error at the items instead.
      if (isItems && fields.subject && !subject.trim()) fields["items.0.item_name"] ??= "Name at least one item";
      setErrors(fields);
      setFormError(err.message);
      if (fields.location || fields.related_asset || fields.delivery_location || (fields.subject && isItems && subject)) setMore(true);
      setBusy(null);
    }
  }

  async function removeExisting(attId: number, url: string) {
    try {
      await api(url, { method: "DELETE" });
      setExisting((cur) => cur.filter((a) => a.id !== attId));
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }

  const err = (k: string) => errors[k];
  const setItem = (key: string, patch: Partial<ItemDraft>) => setItems((cur) => cur.map((i) => (i.key === key ? { ...i, ...patch } : i)));
  const head = opts?.requester.department_head;

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void save(true);
      }}
      className="mt-6 max-w-[680px] lg:mt-8"
    >
      <div className="flex flex-col gap-9 rounded-[var(--radius-panel)] border border-line bg-sheet p-4 sm:p-6">
        {returned && (
          <section className="-m-1 rounded-[var(--radius-ctl)] bg-canvas p-4 ring-1 ring-ink">
            <p className="flex items-center gap-2 text-[15px] font-bold">
              <span className="size-3 rounded-full border-[2.5px] border-accent" aria-hidden="true" />
              {returnStep?.decided_by?.name ?? "An approver"} asked for changes
            </p>
            <p className="mt-1.5 whitespace-pre-line text-[14.5px] leading-relaxed text-ink-2">“{returnStep?.comment}”</p>
            <Field label="Your reply" required htmlFor="reply" className="mt-4" error={err("message")}>
              <Textarea id="reply" rows={2} value={reply} onChange={(e) => setReply(e.target.value)} invalid={!!err("message")} placeholder="Say what you changed" />
            </Field>
          </section>
        )}

        {!isItems ? (
          <>
            <Step title="What kind of problem?">
              <div role="radiogroup" aria-label="Category" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {(opts?.concern_categories ?? Object.keys(CATEGORY_ICON)).map((c) => {
                  const Icon = CATEGORY_ICON[c] ?? CircleHelp;
                  const on = category === c;
                  return (
                    <label
                      key={c}
                      className={cn(
                        "flex min-h-12 cursor-pointer items-center gap-2.5 rounded-[var(--radius-ctl)] border px-3 py-2 text-[14px] font-medium transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60",
                        on ? "border-ink bg-ink text-white" : err("category") ? "border-danger/50 text-ink-2" : "border-line text-ink-2 hover:border-edge hover:text-ink",
                      )}
                    >
                      <input type="radio" name="category" className="sr-only" checked={on} onChange={() => setCategory(c)} />
                      <Icon className="size-[18px] shrink-0" strokeWidth={1.75} aria-hidden="true" />
                      <span className="leading-tight">{c}</span>
                    </label>
                  );
                })}
              </div>
              {err("category") && (
                <p role="alert" className="text-[12.5px] text-danger">
                  Pick the closest one.
                </p>
              )}
            </Step>

            <Step title="What's wrong?">
              <Field label="In a few words" required htmlFor="subject" error={err("subject")}>
                <Input id="subject" value={subject} maxLength={300} onChange={(e) => setSubject(e.target.value)} invalid={!!err("subject")} placeholder="e.g. Aircon leaking in the sales area" />
              </Field>
              <Field label="Details" required htmlFor="description" error={err("description")}>
                <Textarea id="description" rows={4} value={description} onChange={(e) => setDescription(e.target.value)} invalid={!!err("description")} placeholder="What happened, since when, and who is affected" />
              </Field>
              <Field label="Where?" htmlFor="location" error={err("location")}>
                <Input id="location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Floor, room or site" />
              </Field>
            </Step>
          </>
        ) : (
          <>
            <Step title="What do you need?">
              <Segmented<Kind>
                label="Request type"
                value={kind}
                onChange={setKind}
                options={[
                  { value: "supplies", label: "Supplies", icon: Package },
                  { value: "asset", label: "Equipment", icon: ShoppingCart },
                  { value: "local_purchase", label: "Local purchase", icon: Store },
                ]}
              />
              {err("items") && (
                <p role="alert" className="text-[12.5px] text-danger">
                  {err("items")}
                </p>
              )}
              <ol className="flex flex-col gap-3">
                {items.map((it, idx) => (
                  <li key={it.key} className="rounded-[var(--radius-ctl)] border border-line p-3 sm:p-4">
                    <div className="grid grid-cols-[minmax(0,1fr)_76px_96px] items-start gap-2 sm:gap-3">
                      <Field label={items.length > 1 ? `Item ${idx + 1}` : "Item"} required htmlFor={`name-${it.key}`} error={err(`items.${idx}.item_name`)}>
                        <Input id={`name-${it.key}`} value={it.item_name} onChange={(e) => setItem(it.key, { item_name: e.target.value })} invalid={!!err(`items.${idx}.item_name`)} placeholder="e.g. Bond paper A4" />
                      </Field>
                      <Field label="Qty" required htmlFor={`qty-${it.key}`} error={err(`items.${idx}.quantity`)}>
                        <Input id={`qty-${it.key}`} inputMode="numeric" className="tabular" value={it.quantity} onChange={(e) => setItem(it.key, { quantity: e.target.value.replace(/[^0-9]/g, "") })} invalid={!!err(`items.${idx}.quantity`)} />
                      </Field>
                      <Field label="Unit" required htmlFor={`unit-${it.key}`} error={err(`items.${idx}.unit`)}>
                        <Select id={`unit-${it.key}`} value={it.unit} onChange={(e) => setItem(it.key, { unit: e.target.value })}>
                          {(opts?.units ?? ["pc"]).map((u) => (
                            <option key={u}>{u}</option>
                          ))}
                        </Select>
                      </Field>
                    </div>
                    <div className="mt-1 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => setItem(it.key, { open: !it.open })}
                        aria-expanded={it.open}
                        className="-ml-1 inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-ctl)] px-1 text-[13px] font-medium text-ink-3 hover:text-ink"
                      >
                        <ChevronDown className={cn("size-4 transition-transform duration-200", it.open && "rotate-180")} strokeWidth={1.75} aria-hidden="true" />
                        Brand, model, notes
                      </button>
                      {items.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setItems((cur) => cur.filter((x) => x.key !== it.key))}
                          aria-label={`Remove item ${idx + 1}`}
                          className="flex size-9 items-center justify-center rounded-[var(--radius-ctl)] text-ink-3 hover:bg-hover hover:text-danger"
                        >
                          <Trash2 className="size-4" strokeWidth={1.75} />
                        </button>
                      )}
                    </div>
                    {it.open && (
                      <div className="mt-2 grid gap-3 sm:grid-cols-3">
                        <Field label="Brand" htmlFor={`brand-${it.key}`}>
                          <Input id={`brand-${it.key}`} value={it.brand} onChange={(e) => setItem(it.key, { brand: e.target.value })} />
                        </Field>
                        <Field label="Model" htmlFor={`model-${it.key}`}>
                          <Input id={`model-${it.key}`} value={it.model} onChange={(e) => setItem(it.key, { model: e.target.value })} />
                        </Field>
                        <Field label="Category" htmlFor={`cat-${it.key}`}>
                          <Select id={`cat-${it.key}`} value={it.item_category} onChange={(e) => setItem(it.key, { item_category: e.target.value })}>
                            <option value="">—</option>
                            {opts?.supply_categories.map((c) => (
                              <option key={c}>{c}</option>
                            ))}
                          </Select>
                        </Field>
                        <Field label="Notes" htmlFor={`desc-${it.key}`} className="sm:col-span-3">
                          <Input id={`desc-${it.key}`} value={it.description} onChange={(e) => setItem(it.key, { description: e.target.value })} />
                        </Field>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
              <Button size="sm" variant="ghost" icon={Plus} onClick={() => setItems((cur) => [...cur, newItem()])} disabled={items.length >= 100} className="self-start">
                Add another item
              </Button>
            </Step>

            <Step title="Why and when?">
              <Field label="What is it for?" required htmlFor="purpose" error={err("purpose")}>
                <Input id="purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} invalid={!!err("purpose")} placeholder="e.g. Monthly sales reports" />
              </Field>
              <Field label="Needed by" required htmlFor="needed" error={err("needed_by")} className="sm:max-w-[260px]">
                <Input id="needed" type="date" min={today} value={neededBy} onChange={(e) => setNeededBy(e.target.value)} invalid={!!err("needed_by")} />
              </Field>
            </Step>
          </>
        )}

        <Step title={isItems ? "Quotation or photo" : "Photo or file"}>
          {(existing.length > 0 || files.length > 0) && (
            <ul className="flex flex-col gap-1.5">
              {existing.map((a) => (
                <FileRow key={a.id} name={a.filename} meta={fmtSize(a.size)} onRemove={() => removeExisting(a.id, a.url)} />
              ))}
              {files.map((f, i) => (
                <FileRow key={`${f.name}-${i}`} name={f.name} meta={fmtSize(f.size)} onRemove={() => setFiles((cur) => cur.filter((_, j) => j !== i))} />
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            <label className="flex min-h-12 cursor-pointer items-center gap-2.5 rounded-[var(--radius-ctl)] border border-dashed border-edge px-4 text-[14px] font-medium text-ink-2 transition-colors duration-150 hover:border-ink-3 hover:text-ink has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60">
              <Camera className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
              Take photo
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="sr-only"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) addFiles([new File([await shrink(f)], `photo-${Date.now()}.jpg`, { type: "image/jpeg" })]);
                }}
              />
            </label>
            <label className="flex min-h-12 cursor-pointer items-center gap-2.5 rounded-[var(--radius-ctl)] border border-dashed border-edge px-4 text-[14px] font-medium text-ink-2 transition-colors duration-150 hover:border-ink-3 hover:text-ink has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60">
              <Paperclip className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
              Add a file
              <input type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => (addFiles(e.target.files), (e.target.value = ""))} />
            </label>
          </div>
          <p className="text-[12.5px] text-ink-3">Optional · up to {MAX_MB} MB each. A photo helps Admin see exactly what you need or what is broken.</p>
        </Step>

        <section>
          <button
            type="button"
            onClick={() => setMore((m) => !m)}
            aria-expanded={more}
            aria-controls="more-options"
            className="-ml-1 inline-flex h-10 items-center gap-2 rounded-[var(--radius-ctl)] px-1 text-[14.5px] font-bold"
          >
            <ChevronDown className={cn("size-[18px] transition-transform duration-200", more && "rotate-180")} strokeWidth={2} aria-hidden="true" />
            More options
            {!more && <span className="text-[13px] font-normal text-ink-3">{isItems ? "priority, delivery, title" : "priority, date, asset"}</span>}
          </button>
          {more && (
            <div id="more-options" className="mt-4 flex flex-col gap-5">
              <Field label="How urgent?" hint="Executive Admin may adjust this after review.">
                <Segmented<Priority> label="Priority" value={priority} onChange={setPriority} options={PRIORITIES} />
              </Field>
              {!isItems ? (
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Needed by" htmlFor="needed" error={err("needed_by")}>
                    <Input id="needed" type="date" min={today} value={neededBy} onChange={(e) => setNeededBy(e.target.value)} invalid={!!err("needed_by")} />
                  </Field>
                  <Field label="Related asset" htmlFor="asset" hint="Tag or serial, if you know it">
                    <Input id="asset" value={relatedAsset} onChange={(e) => setRelatedAsset(e.target.value)} />
                  </Field>
                </div>
              ) : (
                <>
                  <Field label="Deliver to" htmlFor="delivery">
                    <Input id="delivery" value={delivery} onChange={(e) => setDelivery(e.target.value)} placeholder="Where should it be dropped off?" />
                  </Field>
                  <Field label="Title" htmlFor="subject" hint={autoTitle ? `Leave empty to use “${autoTitle}”` : "Leave empty to use the first item's name"} error={err("subject")}>
                    <Input id="subject" value={subject} maxLength={300} onChange={(e) => setSubject(e.target.value)} />
                  </Field>
                  <Field label="Notes for Executive Admin" htmlFor="description">
                    <Textarea id="description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
                  </Field>
                </>
              )}
            </div>
          )}
        </section>
      </div>

      {formError && (
        <p role="alert" className="mt-4 rounded-[var(--radius-ctl)] border border-danger/30 bg-danger-soft px-4 py-3 text-[14px] text-danger">
          {formError}
        </p>
      )}

      <p className="mt-4 text-[13px] leading-relaxed text-ink-3">
        Sent as <span className="font-medium text-ink-2">{opts?.requester.name ?? "you"}</span>
        {opts?.requester.department ? `, ${opts.requester.department}` : ""}. {head ? `${head} reviews it first.` : "It goes to your approvers first."} You can follow every step in My requests.
      </p>

      <div className="sticky bottom-[calc(var(--tabbar-h)+env(safe-area-inset-bottom))] z-10 -mx-4 mt-3 flex items-center gap-2 border-t border-line bg-canvas/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:px-0 lg:bottom-0">
        <Button type="submit" variant="primary" icon={Send} busy={busy === "submit"} disabled={busy !== null} className="flex-1 sm:flex-none sm:px-6">
          {returned ? "Send again" : "Send request"}
        </Button>
        {!returned && (
          <Button variant="ghost" busy={busy === "draft"} disabled={busy !== null} onClick={() => save(false)}>
            Save draft
          </Button>
        )}
      </div>
    </form>
  );
}

function FileRow({ name, meta, onRemove }: { name: string; meta: string; onRemove: () => void }) {
  return (
    <li className="flex items-center gap-3 rounded-[var(--radius-ctl)] bg-canvas px-3 py-2">
      <Paperclip className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-[13.5px]">{name}</span>
      <span className="tabular text-[12px] text-ink-3">{meta}</span>
      <button type="button" onClick={onRemove} aria-label={`Remove ${name}`} className="flex size-9 items-center justify-center rounded-[6px] text-ink-3 hover:bg-hover hover:text-danger">
        <X className="size-4" strokeWidth={1.75} />
      </button>
    </li>
  );
}
