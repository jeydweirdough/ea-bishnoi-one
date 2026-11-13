"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { api, qs, useApi, type ApiError, type Person } from "@/lib/api";
import { Button, Field, Input, Select } from "@/components/ui/controls";

type DirPerson = Person & { role: string; approver: boolean; gender?: string | null; age?: number | null; added?: boolean };

/** Name parts, sex and date of birth for a new person (typed, or read from a passport). */
export type PersonDraft = { first_name?: string; middle_name?: string; last_name?: string; suffix?: string; gender?: string; birth_date?: string; age?: string };

const ADD = "__add";
const SUFFIXES = ["Jr.", "Sr.", "II", "III", "IV", "V"];
const GENDER: Record<string, string> = { male: "Male", female: "Female", unspecified: "Prefer not to say" };

function ageFrom(birth: string): number | null {
  if (!birth) return null;
  const b = new Date(birth + "T00:00:00");
  if (Number.isNaN(b.getTime())) return null;
  const t = new Date();
  return t.getFullYear() - b.getFullYear() - (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate()) ? 1 : 0);
}

/**
 * Directory-backed select. `role` narrows to staff; `approvers` to people holding an approval grant.
 * `allowAdd` lets staff add someone who is not in the directory yet (guest, new hire, family member);
 * `draft` pre-fills that form, e.g. from a scanned passport whose holder is not in the list.
 */
export function PeoplePicker({
  value,
  onChange,
  role,
  approvers,
  id,
  invalid,
  placeholder = "Choose a person",
  exclude,
  allowAdd,
  draft,
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  role?: string[];
  approvers?: boolean;
  id?: string;
  invalid?: boolean;
  placeholder?: string;
  exclude?: number[];
  allowAdd?: boolean;
  draft?: PersonDraft | null;
}) {
  const people = useApi<DirPerson[]>(`/api/v1/directory${qs({ role, approvers, limit: 50, include: value ?? undefined })}`);
  const [adding, setAdding] = useState(false);
  const [seenDraft, setSeenDraft] = useState<PersonDraft | null | undefined>(draft);
  const [initial, setInitial] = useState<PersonDraft>({});
  if (draft !== seenDraft) {
    setSeenDraft(draft);
    if (draft && allowAdd && !value) {
      setInitial(draft);
      setAdding(true);
    }
  }
  const selected = people.data?.find((p) => p.id === value);
  const details = selected ? [selected.gender ? GENDER[selected.gender] : null, selected.age != null ? `${selected.age} years old` : null].filter(Boolean) : [];

  return (
    <div className="flex flex-col gap-2">
      <Select
        id={id}
        value={value ?? ""}
        invalid={invalid}
        onChange={(e) => {
          if (e.target.value === ADD) {
            setInitial({});
            setAdding(true);
            return;
          }
          onChange(e.target.value ? Number(e.target.value) : null);
        }}
      >
        <option value="">{people.loading && !people.data ? "Loading…" : placeholder}</option>
        {people.data
          ?.filter((p) => !exclude?.includes(p.id))
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.designation ? ` — ${p.designation}` : p.added ? " — Added in Executive Admin" : ""}
            </option>
          ))}
        {allowAdd && people.data && <option value={ADD}>+ Add a person not in the list…</option>}
      </Select>
      {details.length > 0 && !adding && <p className="text-[12.5px] text-ink-3">{details.join(" · ")}</p>}
      {adding && (
        <AddPerson
          idPrefix={id ?? "person"}
          initial={initial}
          onCancel={() => setAdding(false)}
          onAdded={(p) => {
            setAdding(false);
            people.reload();
            onChange(p.id);
          }}
        />
      )}
    </div>
  );
}

function AddPerson({ idPrefix, initial, onCancel, onAdded }: { idPrefix: string; initial: PersonDraft; onCancel: () => void; onAdded: (p: { id: number }) => void }) {
  const [v, setV] = useState<PersonDraft>({ suffix: "", gender: "", birth_date: "", age: "", middle_name: "", ...initial });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string>();
  const [existing, setExisting] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof PersonDraft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setV({ ...v, [k]: e.target.value });
  const computedAge = ageFrom(v.birth_date ?? "");
  const ready = Boolean(v.first_name?.trim() && v.last_name?.trim());
  const fid = (k: string) => `${idPrefix}-new-${k}`;

  async function save(allowDuplicate = false) {
    setBusy(true);
    setErrors({});
    setMessage(undefined);
    setExisting(null);
    try {
      const p = await api<{ id: number }>("/api/v1/directory/people", {
        method: "POST",
        json: {
          first_name: v.first_name?.trim(),
          middle_name: v.middle_name?.trim() || null,
          last_name: v.last_name?.trim(),
          suffix: v.suffix || null,
          gender: v.gender || null,
          birth_date: v.birth_date || null,
          age: v.birth_date ? null : v.age ? Number(v.age) : null,
          allow_duplicate: allowDuplicate,
        },
      });
      onAdded(p);
    } catch (e) {
      const err = e as ApiError;
      setErrors(err.fields ?? {});
      setMessage(err.message);
      if (err.status === 409 && typeof err.data?.existing_id === "number") setExisting(err.data.existing_id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-[var(--radius-ctl)] border border-line bg-canvas p-3" role="group" aria-label="Add a person">
      <p className="flex items-center gap-2 text-[13.5px] font-bold">
        <UserPlus className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" /> Add a person
      </p>
      {Object.keys(initial).length > 0 && <p className="mt-0.5 text-[12.5px] text-ink-3">Filled from the document. Please review.</p>}
      <div className="mb-3" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="First name" required htmlFor={fid("first")} error={errors.first_name}>
          <Input id={fid("first")} value={v.first_name ?? ""} onChange={set("first_name")} autoComplete="off" />
        </Field>
        <Field label="Middle name" htmlFor={fid("middle")}>
          <Input id={fid("middle")} value={v.middle_name ?? ""} onChange={set("middle_name")} autoComplete="off" />
        </Field>
        <Field label="Last name" required htmlFor={fid("last")} error={errors.last_name}>
          <Input id={fid("last")} value={v.last_name ?? ""} onChange={set("last_name")} autoComplete="off" />
        </Field>
        <Field label="Suffix" htmlFor={fid("suffix")}>
          <Select id={fid("suffix")} value={v.suffix ?? ""} onChange={set("suffix")}>
            <option value="">None</option>
            {SUFFIXES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <Field label="Gender" htmlFor={fid("gender")}>
          <Select id={fid("gender")} value={v.gender ?? ""} onChange={set("gender")}>
            <option value="">—</option>
            {Object.entries(GENDER).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-[minmax(0,1fr)_88px] gap-3">
          <Field label="Date of birth" htmlFor={fid("birth")} error={errors.birth_date}>
            <Input id={fid("birth")} type="date" value={v.birth_date ?? ""} onChange={set("birth_date")} />
          </Field>
          <Field label="Age" htmlFor={fid("age")} error={errors.age}>
            <Input
              id={fid("age")}
              inputMode="numeric"
              className="tabular"
              disabled={Boolean(v.birth_date)}
              value={computedAge != null ? String(computedAge) : (v.age ?? "")}
              onChange={(e) => setV({ ...v, age: e.target.value.replace(/[^0-9]/g, "").slice(0, 3) })}
            />
          </Field>
        </div>
      </div>
      <p className="mt-2 text-[12px] text-ink-3">Age comes from the date of birth. If the date isn&rsquo;t known, enter the age instead. Added people can be chosen on forms but cannot sign in.</p>
      {message && (
        <p role="alert" className="mt-2 text-[13px] text-danger">
          {message}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {existing ? (
          <>
            <Button size="sm" variant="primary" onClick={() => onAdded({ id: existing })}>
              Use the existing person
            </Button>
            <Button size="sm" busy={busy} onClick={() => save(true)}>
              Add as a different person
            </Button>
          </>
        ) : (
          <Button size="sm" variant="primary" icon={UserPlus} busy={busy} disabled={!ready} onClick={() => save()}>
            Add person
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
