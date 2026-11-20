"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { api, invalidate, useApi, type ApiError } from "@/lib/api";
import { Button, Field, Input, Segmented, Select, Textarea } from "./controls";
import { Dialog, useToast } from "./feedback";
import { ChosenFile, FileDrop } from "./file-drop";
import { PendingPhotos, uploadPhoto, type PhotoOwner } from "./photos";
import { uploadProof } from "./proof-list";
import { PeoplePicker, type PersonDraft } from "@/components/requests/people-picker";
import { cn } from "@/lib/cn";

export type FieldDef = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "number" | "money" | "date" | "select" | "choice" | "person" | "department" | "vehicle";
  options?: (string | { value: string; label: string })[];
  required?: boolean;
  hint?: string;
  placeholder?: string;
  /** Shown under "More options" so the dialog opens short. */
  more?: boolean;
  half?: boolean;
  min?: string;
  /** Person fields: allow adding someone who is not in the directory. Defaults on for the person a record is about. */
  allowAdd?: boolean;
  /** Only shown (and sent) when this returns true for the current values. */
  show?: (v: Values) => boolean;
  /** Text fields: common answers as one-tap chips under the box, so most people never type it. */
  suggest?: string[];
};

const visible = (f: FieldDef, v: Values) => !f.show || f.show(v);

/** Fields that name the person a record is about (not a staff role), so new people may be added there. */
const SUBJECT_PERSON = new Set(["passenger_id", "guest_id", "employee_id", "assigned_driver_id", "assigned_user_id", "custodian_id", "issued_to_id"]);

export type Values = Record<string, string>;

/** Turn form strings into API values: empty → null, numbers parsed, money kept as a decimal string. */
export function toPayload(fields: FieldDef[], v: Values) {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (!visible(f, v)) continue;
    const raw = (v[f.name] ?? "").trim();
    if (raw === "") out[f.name] = null;
    else if (f.type === "number" || f.type === "person" || f.type === "department" || f.type === "vehicle") out[f.name] = Number(raw);
    else if (f.type === "money") out[f.name] = raw.replace(/,/g, "");
    else out[f.name] = raw;
  }
  return out;
}

export function fromRecord(fields: FieldDef[], rec: Record<string, unknown> | undefined): Values {
  const v: Values = {};
  for (const f of fields) {
    const x = rec?.[f.name] ?? rec?.[f.name.replace(/_id$/, "")];
    if (x && typeof x === "object" && "id" in (x as object)) v[f.name] = String((x as { id: number }).id);
    else v[f.name] = x === null || x === undefined ? "" : String(x);
  }
  return v;
}

function Control({ f, value, onChange, invalid, draft }: { f: FieldDef; value: string; onChange: (v: string) => void; invalid: boolean; draft?: PersonDraft | null }) {
  const id = `rf-${f.name}`;
  switch (f.type) {
    case "textarea":
      return <Textarea id={id} rows={3} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid} placeholder={f.placeholder} />;
    case "choice":
      return (
        <Segmented
          label={f.label}
          value={value}
          onChange={onChange}
          options={(f.options ?? []).map((o) => (typeof o === "string" ? { value: o, label: o } : o))}
        />
      );
    case "select":
      return (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid}>
          {!f.required && <option value="">—</option>}
          {f.required && !value && <option value="">Choose…</option>}
          {f.options?.map((o) => (typeof o === "string" ? <option key={o}>{o}</option> : <option key={o.value} value={o.value}>{o.label}</option>))}
        </Select>
      );
    case "person":
      return (
        <PeoplePicker
          id={id}
          value={value ? Number(value) : null}
          onChange={(n) => onChange(n ? String(n) : "")}
          invalid={invalid}
          placeholder={f.placeholder ?? "Nobody"}
          allowAdd={f.allowAdd ?? SUBJECT_PERSON.has(f.name)}
          draft={(f.allowAdd ?? SUBJECT_PERSON.has(f.name)) ? draft : undefined}
        />
      );
    case "department":
      return <DepartmentPicker id={id} value={value} onChange={onChange} />;
    case "vehicle":
      return <VehiclePicker id={id} value={value} onChange={onChange} invalid={invalid} />;
    case "money":
      return (
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[14px] text-ink-3">₱</span>
          <Input id={id} inputMode="decimal" className="tabular pl-7" value={value} onChange={(e) => onChange(e.target.value.replace(/[^0-9.,]/g, ""))} invalid={invalid} placeholder={f.placeholder} />
        </div>
      );
    case "number":
      return <Input id={id} inputMode="numeric" className="tabular" value={value} onChange={(e) => onChange(e.target.value.replace(/[^0-9]/g, ""))} invalid={invalid} placeholder={f.placeholder} />;
    case "date":
      return <Input id={id} type="date" min={f.min} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid} />;
    default:
      if (f.suggest?.length)
        return (
          <div className="flex flex-col gap-2">
            <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid} placeholder={f.placeholder} />
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={`Common ${f.label.toLowerCase()}`}>
              {f.suggest.slice(0, 6).map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={value === s}
                  onClick={() => onChange(s)}
                  className={cn(
                    "h-8 rounded-full border px-3 text-[13px] font-medium transition-colors duration-150",
                    value === s ? "border-ink bg-ink text-white" : "border-line bg-sheet text-ink-2 hover:border-edge hover:text-ink",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        );
      return <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid} placeholder={f.placeholder} />;
  }
}

function DepartmentPicker({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  const q = useApi<{ id: number; name: string; company: string }[]>("/api/v1/directory/departments");
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">—</option>
      {q.data?.map((d) => (
        <option key={d.id} value={d.id}>
          {d.name} · {d.company}
        </option>
      ))}
    </Select>
  );
}

function VehiclePicker({ id, value, onChange, invalid }: { id: string; value: string; onChange: (v: string) => void; invalid: boolean }) {
  const q = useApi<{ items: { id: number; label: string }[] }>("/api/v1/fleet/vehicles?page_size=200");
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} invalid={invalid}>
      <option value="">No vehicle</option>
      {q.data?.items.map((v) => (
        <option key={v.id} value={v.id}>
          {v.label}
        </option>
      ))}
    </Select>
  );
}

/** Field grid with essentials first and optional fields under "More options". */
export function RecordFields({ fields, values, setValues, errors }: { fields: FieldDef[]; values: Values; setValues: (v: Values) => void; errors: Record<string, string> }) {
  const shown = fields.filter((f) => visible(f, values));
  const main = shown.filter((f) => !f.more);
  const extra = shown.filter((f) => f.more);
  const hasExtraValue = extra.some((f) => values[f.name] || errors[f.name]);
  const [more, setMore] = useState(hasExtraValue);
  const [seen, setSeen] = useState(hasExtraValue);
  if (hasExtraValue !== seen) {
    setSeen(hasExtraValue);
    if (hasExtraValue) setMore(true);
  }
  const grid = (list: FieldDef[]) => (
    <div className="grid gap-4 sm:grid-cols-2">
      {list.map((f) => (
        <Field key={f.name} label={f.label} required={f.required} hint={f.hint} error={errors[f.name]} htmlFor={`rf-${f.name}`} className={cn(!f.half && "sm:col-span-2")}>
          <Control f={f} value={values[f.name] ?? ""} onChange={(v) => setValues({ ...values, [f.name]: v })} invalid={Boolean(errors[f.name])} />
        </Field>
      ))}
    </div>
  );
  return (
    <div className="flex flex-col gap-4">
      {grid(main)}
      {extra.length > 0 && (
        <>
          <button type="button" onClick={() => setMore((m) => !m)} aria-expanded={more} className="-ml-1 inline-flex h-10 items-center gap-2 self-start px-1 text-[14px] font-bold">
            <ChevronDown className={cn("size-4 transition-transform duration-200", more && "rotate-180")} strokeWidth={2} aria-hidden="true" />
            More options
            {!more && <span className="text-[13px] font-normal text-ink-3">{extra.map((f) => f.label.toLowerCase()).slice(0, 3).join(", ")}</span>}
          </button>
          {more && grid(extra)}
        </>
      )}
    </div>
  );
}

/**
 * A dialog that edits a record described by `fields`. `onSubmit` throws an ApiError on failure; it may
 * return the saved record so a scanned document can be attached to it.
 * `scan` adds "Upload the document": the file is read and the form filled for the user to review.
 */
export function RecordDialog({
  open,
  onClose,
  title,
  description,
  fields,
  initial,
  submitLabel = "Save",
  onSubmit,
  attach,
  photos,
  proof,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  fields: FieldDef[];
  initial?: Values;
  submitLabel?: string;
  onSubmit: (payload: Record<string, unknown>) => Promise<unknown>;
  /** "Attach the document": one file (PDF or photo) attached to the saved record (or to `ownerId`). Nothing is read from it. */
  attach?: { ownerType: string; ownerId?: number; title?: string };
  /** Lets the user take or pick photos of the new item; uploaded after it is saved (onSubmit must return it). */
  photos?: PhotoOwner;
  /**
   * Optional photo proof of the transaction the save creates: the camera stamps date, time and location.
   * `url` gets the saved result and returns where to send the photos.
   */
  proof?: { url: (saved: unknown) => string | null | undefined; when?: (values: Values) => boolean; title?: string; note?: string; label?: string };
}) {
  const toast = useToast();
  const [values, setValues] = useState<Values>(initial ?? {});
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState<File[]>([]);
  const [proofs, setProofs] = useState<File[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState(false);
  // Reset the form the moment it opens (during render, so it never shows the previous values first).
  // Only when it opens: callers often pass a fresh `initial` object each render.
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setValues(initial ?? {});
      setFile(null);
      setPending([]);
      setProofs([]);
      setErrors({});
      setMessage(undefined);
    }
  }

  const missing = fields.some((f) => f.required && visible(f, values) && !(values[f.name] ?? "").trim());

  async function submit() {
    setBusy(true);
    setErrors({});
    setMessage(undefined);
    try {
      const saved = (await onSubmit(toPayload(fields, values))) as { id?: number; created?: { id: number }[]; photo_owner?: PhotoOwner } | undefined;
      const ownerId = attach?.ownerId ?? saved?.id;
      if (file && attach && ownerId) {
        const fd = new FormData();
        fd.set("owner_type", attach.ownerType);
        fd.set("owner_id", String(ownerId));
        fd.set("file", file);
        await api("/api/v1/attachments", { method: "POST", body: fd }).catch((e: ApiError) => toast(`Saved, but the document was not attached: ${e.message}`, "error"));
      }
      if (photos && pending.length && saved?.id) {
        // Several identical items registered at once share the photos (up to 20 records).
        const owners = saved.created?.length ? saved.created.slice(0, 20).map((c) => c.id) : [saved.id];
        for (const id of owners) for (const f of pending) await uploadPhoto(saved.photo_owner ?? photos, id, f).catch((e: ApiError) => toast(`Saved, but a photo was not added: ${e.message}`, "error"));
        invalidate();
      }
      const showProof = proof && (!proof.when || proof.when(values));
      const target = showProof && proofs.length ? proof.url(saved) : null;
      if (target) {
        let added = 0;
        for (const f of proofs) {
          await uploadProof(target, f)
            .then(() => added++)
            .catch((e: ApiError) => toast(`Saved, but a proof photo was not added: ${e.message}`, "error"));
        }
        if (added) invalidate();
      }
      onClose();
    } catch (e) {
      const err = e as ApiError;
      setErrors(err.fields ?? {});
      setMessage(Object.keys(err.fields ?? {}).some((k) => fields.some((f) => f.name === k)) ? undefined : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title={title}
      description={description}
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" busy={busy} disabled={missing} onClick={submit}>
            {submitLabel}
          </Button>
        </>
      }
    >
      {attach && (
        <FileDrop
          accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,image/*"
          multiple={false}
          className="mb-5"
          title={attach.title ?? "Attach the document"}
          hint="optional · PDF or photo, up to 10 MB. It is saved with the record."
          inputLabel="Document file"
          onFiles={(f) => setFile(f[0])}
        >
          {file && <ChosenFile file={file} onRemove={() => setFile(null)} />}
        </FileDrop>
      )}
      {photos && <PendingPhotos files={pending} onChange={setPending} />}
      <RecordFields
        fields={fields}
        values={values}
        errors={errors}
        setValues={setValues}
      />
      {proof && (!proof.when || proof.when(values)) && (
        <div className="mt-5 [&>div]:mb-0">
          <PendingPhotos files={proofs} onChange={setProofs} max={6} title={proof.title ?? "Photo proof"} note={proof.note ?? "optional · date, time and location are stamped on camera photos"} showMain={false} stamp={proof.label ?? title} />
        </div>
      )}
      {message && (
        <p role="alert" className="mt-4 text-[13.5px] text-danger">
          {message}
        </p>
      )}
    </Dialog>
  );
}
