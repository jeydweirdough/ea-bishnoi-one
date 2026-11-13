"use client";

import Link from "next/link";
import { useState } from "react";
import { BedDouble, BookUser, Check, ChevronRight, CircleCheck, Globe, IdCard, ListChecks, Lock, Pencil, Plane, Plus, Ticket, X, Ban, type LucideIcon } from "lucide-react";
import { api, fmtDate, invalidate, post, qs, useApi, type ApiError, type Attachment, type Page, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Chip } from "@/components/ui/controls";
import { EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { RecordAttachments } from "@/components/assets/assets";
import { DueLabel } from "@/components/fleet/fleet";
import { DocumentsPanel } from "@/components/documents/documents";
import { useShell } from "@/components/shell/shell-context";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- types */

type CheckItem = { id: number; name: string; description: string | null; country: string | null; done: boolean };
type Flight = {
  id: number;
  reference: string;
  passenger: Person;
  travel_type: "domestic" | "international";
  origin: string;
  destination: string;
  destination_country: string | null;
  departure_date: string;
  return_date: string | null;
  airline: string | null;
  booking_reference: string | null;
  status: "requested" | "booked" | "ticketed" | "completed" | "cancelled";
  purpose: string | null;
  notes: string | null;
  days_to_departure: number;
  checklist: CheckItem[];
  checklist_done: number;
  checklist_total: number;
};
type Hotel = { id: number; reference: string; guest: Person; flight_id: number | null; hotel: string; destination: string; check_in: string; check_out: string; nights: number; booking_reference: string | null; status: "requested" | "booked" | "completed" | "cancelled"; cost_reference: string | null; notes: string | null };
type FlightDetail = Flight & { attachments: Attachment[]; hotels: Hotel[] };
type Doc = {
  id: number;
  reference: string;
  employee: Person;
  doc_type: "passport" | "visa";
  holder_kind: "employee" | "expat";
  visa_type: string | null;
  country: string;
  number_masked: string | null;
  application_date: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  renewal_date: string | null;
  days_to_expiry: number | null;
  status: "applied" | "active" | "for_renewal" | "expired" | "cancelled";
  responsible: Person | null;
  notes: string | null;
  version: number;
};
type Requirement = { id: number; travel_type: "domestic" | "international"; country: string | null; name: string; description: string | null; active: boolean; position: number };

const FLIGHT_LABEL: Record<Flight["status"], string> = { requested: "Requested", booked: "Booked", ticketed: "Ticketed", completed: "Completed", cancelled: "Cancelled" };
const HOTEL_LABEL: Record<Hotel["status"], string> = { requested: "Requested", booked: "Booked", completed: "Completed", cancelled: "Cancelled" };
const DOC_LABEL: Record<Doc["status"], string> = { applied: "Applied", active: "Valid", for_renewal: "For renewal", expired: "Expired", cancelled: "Cancelled" };

function Pill({ children, tone = "ink" }: { children: React.ReactNode; tone?: "ink" | "live" | "mute" | "danger" }) {
  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[12.5px] font-medium whitespace-nowrap",
        tone === "live" && "border-ink bg-sheet",
        tone === "ink" && "border-edge bg-sheet",
        tone === "mute" && "border-line bg-canvas text-ink-3",
        tone === "danger" && "border-danger/30 bg-danger-soft text-danger",
      )}
    >
      {tone === "live" && <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" />}
      {children}
    </span>
  );
}

const flightTone = (s: Flight["status"]) => (s === "requested" ? "live" : s === "cancelled" || s === "completed" ? "mute" : "ink");

/* ---------------------------------------------------------------- flights */

const FLIGHT_FIELDS: FieldDef[] = [
  { name: "passenger_id", label: "Passenger", type: "person", required: true, placeholder: "Choose a person" },
  { name: "travel_type", label: "Travel", type: "select", required: true, half: true, options: [{ value: "domestic", label: "Domestic" }, { value: "international", label: "International" }] },
  { name: "destination_country", label: "Destination country", half: true, hint: "International only" },
  { name: "origin", label: "From", required: true, half: true, placeholder: "e.g. Manila (MNL)" },
  { name: "destination", label: "To", required: true, half: true, placeholder: "e.g. Cebu (CEB)" },
  { name: "departure_date", label: "Departure", type: "date", required: true, half: true },
  { name: "return_date", label: "Return", type: "date", half: true },
  { name: "purpose", label: "Purpose of travel", type: "textarea", more: true },
  { name: "airline", label: "Airline", more: true, half: true },
  { name: "booking_reference", label: "Booking reference (PNR)", more: true, half: true },
  { name: "notes", label: "Notes", type: "textarea", more: true },
];

function FlightRow({ f }: { f: Flight }) {
  return (
    <li>
      <Link href={`/flight/${f.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line sm:mt-0" aria-hidden="true">
          <Plane className="size-5" strokeWidth={1.6} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold">
            {f.origin} → {f.destination}
          </span>
          <span className="block text-[12.5px] text-ink-3">
            {f.passenger.name} · {fmtDate(f.departure_date)}
            {f.return_date ? ` – ${fmtDate(f.return_date)}` : ""} · {f.travel_type === "international" ? f.destination_country : "Domestic"}
          </span>
          {f.checklist_total > 0 && !["ticketed", "completed", "cancelled"].includes(f.status) && (
            <span className={cn("mt-1 inline-flex items-center gap-1 text-[12.5px]", f.checklist_done < f.checklist_total ? "text-ink" : "text-ink-3")}>
              <ListChecks className="size-3.5" strokeWidth={2} aria-hidden="true" />
              {f.checklist_done}/{f.checklist_total} requirements
            </span>
          )}
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1 text-[12.5px]">
          <Pill tone={flightTone(f.status)}>{FLIGHT_LABEL[f.status]}</Pill>
          {!["completed", "cancelled"].includes(f.status) && f.days_to_departure >= 0 && <span className="text-ink-3">{f.days_to_departure === 0 ? "Departs today" : `In ${f.days_to_departure} days`}</span>}
        </span>
        <ChevronRight className="mt-3 hidden size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0 sm:block" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}

export function FlightsPage() {
  const toast = useToast();
  const [state, setState] = useState<"upcoming" | "past">("upcoming");
  const data = useApi<Page<Flight>>(`/api/v1/travel/flights?state=${state}&page_size=100`);
  const [creating, setCreating] = useState(false);
  return (
    <ModuleShell
      group="travel"
      item="flights"
      actions={
        <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
          New booking
        </Button>
      }
    >
      <Panel>
        <div className="flex gap-1.5 border-b border-line p-3 sm:px-5">
          <Chip on={state === "upcoming"} onClick={() => setState("upcoming")}>
            Upcoming
          </Chip>
          <Chip on={state === "past"} onClick={() => setState("past")}>
            Past & cancelled
          </Chip>
        </div>
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState icon={Plane} title={state === "upcoming" ? "No upcoming trips" : "No records yet"} compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((f) => (
              <FlightRow key={f.id} f={f} />
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New flight booking"
        description="The travel requirements for the destination are added as a checklist."
        fields={FLIGHT_FIELDS}
        initial={{ travel_type: "domestic" }}
        submitLabel="Create booking"
        onSubmit={async (p) => {
          const f = await post<Flight>("/api/v1/travel/flights", p);
          toast(`Created · ${f.reference}`);
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

export function FlightDetailView({ id }: { id: number }) {
  const toast = useToast();
  const q = useApi<FlightDetail>(`/api/v1/travel/flights/${id}`);
  const [dialog, setDialog] = useState<null | "edit" | "booked" | "cancelled" | "hotel">(null);
  const [busy, setBusy] = useState(false);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This booking doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const f = q.data;
  if (!f) return <PageFrame><SkeletonRows /></PageFrame>;
  const closed = f.status === "completed" || f.status === "cancelled";
  const ready = f.checklist_done >= f.checklist_total;

  async function setStatus(status: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      q.setData({ ...f!, ...(await post<Flight>(`/api/v1/travel/flights/${f!.id}/status`, { status, ...extra })) });
      toast(`Marked ${status}`);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function tick(item: CheckItem) {
    // Optimistic: the tick shows at once and rolls back if the save fails.
    const before = f!;
    const checklist = before.checklist.map((c) => (c.id === item.id ? { ...c, done: !item.done } : c));
    q.setData({ ...before, checklist, checklist_done: checklist.filter((c) => c.done).length });
    try {
      const saved = await api<Flight>(`/api/v1/travel/flights/${before.id}/checklist/${item.id}`, { method: "PUT", json: { done: !item.done } });
      q.setData({ ...before, ...saved });
    } catch (e) {
      q.setData(before);
      toast((e as ApiError).message, "error");
    }
  }

  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Travel & Immigration", href: "/travel/flights" }, { label: f.reference }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Plane className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {f.reference} · {f.travel_type === "international" ? `International · ${f.destination_country}` : "Domestic"}
            {f.booking_reference ? ` · PNR ${f.booking_reference}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">
            {f.origin} → {f.destination}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[13.5px] text-ink-2">
            <Pill tone={flightTone(f.status)}>{FLIGHT_LABEL[f.status]}</Pill>
            {f.passenger.name} · {fmtDate(f.departure_date)}
            {f.return_date ? ` – ${fmtDate(f.return_date)}` : " (one way)"}
          </div>
        </div>
      </header>

      {!closed && (
        <section className="mt-6 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 sm:p-5">
          <p className="text-[15px] font-bold">
            {f.status === "requested" ? "Book the flight" : f.status === "booked" ? (ready ? "Ready to ticket" : "Finish the requirements before ticketing") : f.status === "ticketed" ? "Ticketed" : ""}
          </p>
          <p className="mt-1 text-[14px] text-ink-2">
            {f.checklist_total ? `${f.checklist_done} of ${f.checklist_total} travel requirements checked.` : "No travel requirements apply."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {f.status === "requested" && (
              <Button variant="primary" icon={Ticket} onClick={() => setDialog("booked")}>
                Mark booked
              </Button>
            )}
            {f.status === "booked" && (
              <Button variant="primary" icon={Ticket} busy={busy} disabled={!ready} onClick={() => setStatus("ticketed")}>
                Mark ticketed
              </Button>
            )}
            {f.status === "ticketed" && (
              <Button variant="primary" icon={CircleCheck} busy={busy} onClick={() => setStatus("completed")}>
                Trip completed
              </Button>
            )}
            <Button icon={BedDouble} onClick={() => setDialog("hotel")}>
              Add hotel
            </Button>
            <Button variant="ghost" icon={Ban} onClick={() => setDialog("cancelled")}>
              Cancel
            </Button>
          </div>
        </section>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Travel requirements" meta={`${f.checklist_done}/${f.checklist_total}`}>
            {f.checklist.length === 0 ? (
              <EmptyState icon={ListChecks} title="No requirements for this destination" compact />
            ) : (
              <ul className="divide-y divide-line">
                {f.checklist.map((c) => (
                  <li key={c.id}>
                    <label className={cn("flex min-h-12 items-start gap-3 px-4 py-3 sm:px-5", !closed && "cursor-pointer hover:bg-canvas")}>
                      <input type="checkbox" className="mt-0.5 size-[18px] shrink-0 accent-[#111]" checked={c.done} disabled={closed} onChange={() => tick(c)} />
                      <span className="min-w-0">
                        <span className={cn("block text-[14px]", c.done ? "text-ink-3 line-through" : "font-medium")}>{c.name}</span>
                        {c.description && <span className="block text-[12.5px] text-ink-3">{c.description}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {f.hotels.length > 0 && (
            <Panel title="Hotels">
              <ul className="divide-y divide-line">
                {f.hotels.map((h) => (
                  <li key={h.id} className="px-4 py-3 text-[13.5px] sm:px-5">
                    <span className="font-medium">{h.hotel}</span> · {fmtDate(h.check_in)} – {fmtDate(h.check_out)} ({h.nights} nights)
                    <span className="block text-[12.5px] text-ink-3">
                      {HOTEL_LABEL[h.status]}
                      {h.booking_reference ? ` · ${h.booking_reference}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
        <aside className="flex flex-col gap-5">
          <Panel title="Trip" actions={!closed ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Airline", f.airline],
                ["Booking ref.", f.booking_reference],
                ["Purpose", f.purpose],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k as string} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
            {f.notes && <p className="whitespace-pre-line border-t border-line px-4 py-3 text-[13px] text-ink-2 sm:px-5">{f.notes}</p>}
          </Panel>
          <DocumentsPanel relatedType="flight" relatedId={f.id} />
          <RecordAttachments ownerType="flight" ownerId={f.id} items={f.attachments} canAdd={!closed} onChange={q.reload} />
        </aside>
      </div>

      <RecordDialog
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        title="Edit booking"
        fields={FLIGHT_FIELDS}
        initial={fromRecord(FLIGHT_FIELDS, { ...f, passenger_id: f.passenger.id } as unknown as Record<string, unknown>)}
        onSubmit={async (p) => {
          await api(`/api/v1/travel/flights/${f.id}`, { method: "PATCH", json: p });
          toast("Saved");
          q.reload();
        }}
      />
      <RecordDialog
        open={dialog === "booked"}
        onClose={() => setDialog(null)}
        title="Mark booked"
        fields={[
          { name: "booking_reference", label: "Booking reference (PNR)", required: true, half: true },
          { name: "airline", label: "Airline", half: true },
        ]}
        initial={{ booking_reference: f.booking_reference ?? "", airline: f.airline ?? "" }}
        submitLabel="Mark booked"
        onSubmit={async (p) => {
          await post(`/api/v1/travel/flights/${f.id}/status`, { ...p, status: "booked" });
          toast("Booked");
          q.reload();
          invalidate();
        }}
      />
      <RecordDialog
        open={dialog === "cancelled"}
        onClose={() => setDialog(null)}
        title="Cancel this booking"
        fields={[{ name: "reason", label: "Reason", type: "textarea", required: true }]}
        submitLabel="Cancel booking"
        onSubmit={async (p) => {
          await post(`/api/v1/travel/flights/${f.id}/status`, { ...p, status: "cancelled" });
          toast("Cancelled");
          q.reload();
          invalidate();
        }}
      />
      <RecordDialog
        open={dialog === "hotel"}
        onClose={() => setDialog(null)}
        title="Add a hotel for this trip"
        fields={HOTEL_FIELDS.filter((x) => x.name !== "guest_id")}
        initial={{ destination: f.destination, check_in: f.departure_date, check_out: f.return_date ?? "" }}
        submitLabel="Add hotel"
        onSubmit={async (p) => {
          await post("/api/v1/travel/hotels", { ...p, guest_id: f.passenger.id, flight_id: f.id });
          toast("Hotel added");
          q.reload();
          invalidate();
        }}
      />
    </PageFrame>
  );
}

/* ---------------------------------------------------------------- hotels */

const HOTEL_FIELDS: FieldDef[] = [
  { name: "guest_id", label: "Guest", type: "person", required: true, placeholder: "Choose a person" },
  { name: "hotel", label: "Hotel", required: true, half: true },
  { name: "destination", label: "City", required: true, half: true },
  { name: "check_in", label: "Check-in", type: "date", required: true, half: true },
  { name: "check_out", label: "Check-out", type: "date", required: true, half: true },
  { name: "booking_reference", label: "Confirmation number", more: true, half: true },
  { name: "cost_reference", label: "Cost reference", more: true, half: true, hint: "Finance / PO reference" },
  { name: "notes", label: "Notes", type: "textarea", more: true },
];

export function HotelsPage() {
  const toast = useToast();
  const [state, setState] = useState<"upcoming" | "past">("upcoming");
  const data = useApi<Hotel[]>(`/api/v1/travel/hotels?state=${state}`);
  const [creating, setCreating] = useState(false);
  const [acting, setActing] = useState<{ h: Hotel; status: "booked" | "completed" | "cancelled" } | null>(null);
  return (
    <ModuleShell
      group="travel"
      item="hotels"
      actions={
        <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
          New reservation
        </Button>
      }
    >
      <Panel>
        <div className="flex gap-1.5 border-b border-line p-3 sm:px-5">
          <Chip on={state === "upcoming"} onClick={() => setState("upcoming")}>
            Upcoming
          </Chip>
          <Chip on={state === "past"} onClick={() => setState("past")}>
            Past & cancelled
          </Chip>
        </div>
        {!data.data ? (
          <SkeletonRows />
        ) : data.data.length === 0 ? (
          <EmptyState icon={BedDouble} title="No reservations" compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.map((h) => (
              <li key={h.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                <span className="flex min-w-0 flex-1 items-start gap-3.5">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line" aria-hidden="true">
                    <BedDouble className="size-5" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[15px] font-bold">
                      {h.hotel} · {h.destination}
                    </span>
                    <span className="block text-[12.5px] text-ink-3">
                      {h.guest.name} · {fmtDate(h.check_in)} – {fmtDate(h.check_out)} · {h.nights} night{h.nights > 1 ? "s" : ""}
                      {h.booking_reference ? ` · ${h.booking_reference}` : ""}
                    </span>
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2 self-start sm:self-center">
                  <Pill tone={h.status === "requested" ? "live" : h.status === "booked" ? "ink" : "mute"}>{HOTEL_LABEL[h.status]}</Pill>
                  {h.status === "requested" && (
                    <Button size="sm" icon={Check} onClick={() => setActing({ h, status: "booked" })}>
                      Booked
                    </Button>
                  )}
                  {h.status === "booked" && (
                    <Button size="sm" icon={CircleCheck} onClick={() => setActing({ h, status: "completed" })}>
                      Stay done
                    </Button>
                  )}
                  {(h.status === "requested" || h.status === "booked") && (
                    <Button size="sm" variant="ghost" icon={X} aria-label="Cancel reservation" onClick={() => setActing({ h, status: "cancelled" })} />
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New hotel reservation"
        fields={HOTEL_FIELDS}
        submitLabel="Create"
        onSubmit={async (p) => {
          await post("/api/v1/travel/hotels", p);
          toast("Reservation created");
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(acting)}
        onClose={() => setActing(null)}
        title={acting?.status === "booked" ? "Mark booked" : acting?.status === "completed" ? "Stay completed" : "Cancel reservation"}
        description={acting ? `${acting.h.hotel} · ${acting.h.guest.name}` : undefined}
        fields={
          acting?.status === "booked"
            ? [{ name: "booking_reference", label: "Confirmation number", required: true }]
            : acting?.status === "cancelled"
              ? [{ name: "reason", label: "Reason", type: "textarea", required: true }]
              : []
        }
        initial={{ booking_reference: acting?.h.booking_reference ?? "" }}
        submitLabel="Save"
        onSubmit={async (p) => {
          await post(`/api/v1/travel/hotels/${acting!.h.id}/status`, { ...p, status: acting!.status });
          toast("Updated");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- passports & visas */

function docFields(kind: "visa" | "passport", holder: "employee" | "expat"): FieldDef[] {
  return [
    { name: "employee_id", label: holder === "expat" ? "Expat employee" : "Employee", type: "person", required: true, placeholder: "Choose a person" },
    ...(kind === "visa" ? [{ name: "visa_type", label: "Visa type", required: true, half: true, placeholder: holder === "expat" ? "e.g. 9(g) work visa" : "e.g. Japan tourist visa" } as FieldDef] : []),
    { name: "country", label: kind === "passport" ? "Issuing country" : "Country", required: true, half: true },
    { name: "expiry_date", label: "Expires", type: "date", half: true, hint: "Required unless still applying" },
    { name: "status", label: "Status", type: "select", required: true, half: true, options: Object.entries(DOC_LABEL).map(([value, label]) => ({ value, label })) },
    { name: "number_last4", label: "Last 4 characters of the number", more: true, half: true, hint: "Never the full number" },
    { name: "application_date", label: "Applied on", type: "date", more: true, half: true },
    { name: "issue_date", label: "Issued on", type: "date", more: true, half: true },
    { name: "renewal_date", label: "Start renewal by", type: "date", more: true, half: true },
    { name: "responsible_id", label: "Responsible", type: "person", more: true, half: true },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
}

function Locked() {
  return <EmptyState icon={Lock} title="Restricted records" body="Passport and visa records need explicit access. An Admin can grant it in Settings › People & access." compact />;
}

function DocList({ docs, onEdit }: { docs: Doc[]; onEdit?: (d: Doc) => void }) {
  return (
    <ul className="divide-y divide-line">
      {docs.map((d) => {
        const I: LucideIcon = d.doc_type === "passport" ? BookUser : d.holder_kind === "expat" ? Globe : IdCard;
        return (
          <li key={d.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
            <span className="flex min-w-0 flex-1 items-start gap-3.5">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line" aria-hidden="true">
                <I className="size-5" strokeWidth={1.6} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[15px] font-bold">
                  {d.employee.name} · {d.doc_type === "passport" ? "Passport" : d.visa_type}
                </span>
                <span className="block text-[12.5px] text-ink-3">
                  {d.country}
                  {d.number_masked ? ` · ${d.number_masked}` : ""} · expires {fmtDate(d.expiry_date)}
                  {d.responsible ? ` · ${d.responsible.name}` : ""}
                </span>
              </span>
            </span>
            <span className="flex items-center gap-3 self-start text-[12.5px] sm:self-center">
              {["active", "for_renewal", "expired"].includes(d.status) && <DueLabel days={d.days_to_expiry} />}
              <Pill tone={d.status === "expired" ? "danger" : d.status === "for_renewal" || d.status === "applied" ? "live" : d.status === "cancelled" ? "mute" : "ink"}>{DOC_LABEL[d.status]}</Pill>
              {onEdit && <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => onEdit(d)} />}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

type DocView = "all" | "expiring" | "passport" | "employee-visa" | "expat-visa";
const DOC_VIEWS: { value: DocView; label: string; query: Record<string, string | number> }[] = [
  { value: "all", label: "All", query: {} },
  { value: "expiring", label: "Expiring in 120 days", query: { expiring_within: 120 } },
  { value: "passport", label: "Passports", query: { doc_type: "passport" } },
  { value: "employee-visa", label: "Employee visas", query: { doc_type: "visa", holder_kind: "employee" } },
  { value: "expat-visa", label: "Expat visas", query: { doc_type: "visa", holder_kind: "expat" } },
];

/** Every passport and visa in one register; expiring, passports and the two visa kinds are filters. */
export function DocumentsPage({ view = "all" }: { view?: DocView }) {
  const toast = useToast();
  const [tab, setTab] = useState<DocView>(view);
  const current = DOC_VIEWS.find((v) => v.value === tab)!;
  const data = useApi<Doc[]>(`/api/v1/travel/documents${qs(current.query)}`);
  const [creating, setCreating] = useState<null | "passport" | "visa">(null);
  const [editing, setEditing] = useState<Doc | null>(null);
  const expat = tab === "expat-visa";
  const visaFields: FieldDef[] = [
    { name: "holder_kind", label: "Visa for", type: "select", required: true, half: true, options: [{ value: "employee", label: "Employee" }, { value: "expat", label: "Expat employee" }] },
    ...docFields("visa", expat ? "expat" : "employee"),
  ];
  return (
    <ModuleShell
      group="travel"
      item="documents"
      actions={
        data.error?.status === 403 ? undefined : (
          <>
            <Button variant="primary" icon={Plus} onClick={() => setCreating("passport")}>
              Add passport
            </Button>
            <Button icon={Plus} onClick={() => setCreating("visa")}>
              {expat ? "Add expat visa" : "Add visa"}
            </Button>
          </>
        )
      }
    >
      <p className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-ink-3">
        <Lock className="size-3.5" strokeWidth={2} aria-hidden="true" /> Sensitive: every view is logged. Only the last 4 characters of a number are kept. Holders and Admins are reminded at 90, 30, 7 and 0 days.
      </p>
      <Panel>
        {data.error?.status !== 403 && (
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto border-b border-line p-3 sm:px-5">
            {DOC_VIEWS.map((v) => (
              <Chip key={v.value} on={tab === v.value} onClick={() => setTab(v.value)}>
                {v.label}
              </Chip>
            ))}
          </div>
        )}
        {data.error?.status === 403 ? (
          <Locked />
        ) : data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.length === 0 ? (
          <EmptyState icon={tab === "expiring" ? CircleCheck : IdCard} title={tab === "expiring" ? "No upcoming expiries" : "No records yet"} compact />
        ) : (
          <DocList docs={data.data} onEdit={setEditing} />
        )}
      </Panel>
      <RecordDialog
        open={Boolean(creating)}
        onClose={() => setCreating(null)}
        title={creating === "passport" ? "Add a passport" : "Add a visa"}
        fields={creating === "passport" ? docFields("passport", "employee") : visaFields}
        initial={{ status: "active", holder_kind: expat ? "expat" : "employee" }}
        submitLabel="Add"
        scan={{ kind: "travel_document", attachTo: "travel_document" }}
        onSubmit={async (p) => {
          const kind = creating!;
          const d = await post<{ id: number }>("/api/v1/travel/documents", { ...p, doc_type: kind, holder_kind: kind === "visa" ? (p.holder_kind ?? "employee") : "employee" });
          toast("Record added");
          invalidate();
          return d;
        }}
      />
      <RecordDialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.doc_type === "passport" ? "passport" : "visa"} · ${editing?.employee.name ?? ""}`}
        fields={editing ? docFields(editing.doc_type, editing.holder_kind) : []}
        initial={editing ? fromRecord(docFields(editing.doc_type, editing.holder_kind), { ...editing, employee_id: editing.employee.id, responsible_id: editing.responsible?.id, number_last4: editing.number_masked?.slice(-4) } as unknown as Record<string, unknown>) : undefined}
        onSubmit={async (p) => {
          await api(`/api/v1/travel/documents/${editing!.id}`, { method: "PATCH", json: { ...p, doc_type: editing!.doc_type, holder_kind: editing!.holder_kind, version: editing!.version } });
          toast("Saved");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- requirements */

const REQ_FIELDS: FieldDef[] = [
  { name: "name", label: "Requirement", required: true },
  { name: "travel_type", label: "Applies to", type: "select", required: true, half: true, options: [{ value: "domestic", label: "Domestic travel" }, { value: "international", label: "International travel" }] },
  { name: "country", label: "Only for country", half: true, hint: "Empty = every destination" },
  { name: "description", label: "Guidance", type: "textarea", more: true },
];

export function RequirementsPage() {
  const toast = useToast();
  const { me } = useShell();
  const admin = me?.role === "admin";
  const data = useApi<Requirement[]>("/api/v1/travel/requirements");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Requirement | null>(null);
  const groups: [string, Requirement[]][] = [
    ["Domestic", (data.data ?? []).filter((r) => r.travel_type === "domestic")],
    ["International — every destination", (data.data ?? []).filter((r) => r.travel_type === "international" && !r.country)],
    ["International — specific countries", (data.data ?? []).filter((r) => r.travel_type === "international" && r.country)],
  ];
  return (
    <ModuleShell
      group="travel"
      item="requirements"
      summary="The checklist each booking must complete before ticketing. Requirements differ by destination, so keep them current."
      actions={
        admin ? (
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Add requirement
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-5">
        {!data.data ? (
          <Panel>
            <SkeletonRows />
          </Panel>
        ) : (
          groups.map(
            ([title, items]) =>
              items.length > 0 && (
                <Panel key={title} title={title} meta={`${items.length}`}>
                  <ul className="divide-y divide-line">
                    {items.map((r) => (
                      <li key={r.id} className="flex items-start gap-3 px-4 py-3 sm:px-5">
                        <ListChecks className={cn("mt-0.5 size-[18px] shrink-0", r.active ? "text-ink-2" : "text-mute")} strokeWidth={1.75} aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className={cn("block text-[14px] font-medium", !r.active && "text-ink-3 line-through")}>
                            {r.name}
                            {r.country ? <span className="font-normal text-ink-3"> · {r.country}</span> : null}
                          </span>
                          {r.description && <span className="block text-[12.5px] text-ink-3">{r.description}</span>}
                        </span>
                        {admin && <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${r.name}`} onClick={() => setEditing(r)} />}
                      </li>
                    ))}
                  </ul>
                </Panel>
              ),
          )
        )}
      </div>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a travel requirement"
        fields={REQ_FIELDS}
        initial={{ travel_type: "international" }}
        onSubmit={async (p) => {
          await post("/api/v1/travel/requirements", { ...p, active: true, position: data.data?.length ?? 0 });
          toast("Requirement added");
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title="Edit requirement"
        fields={[...REQ_FIELDS, { name: "active", label: "In use", type: "select", required: true, options: [{ value: "true", label: "Yes" }, { value: "false", label: "No — retired" }] }]}
        initial={editing ? { ...fromRecord(REQ_FIELDS, editing as unknown as Record<string, unknown>), active: String(editing.active) } : undefined}
        onSubmit={async (p) => {
          await api(`/api/v1/travel/requirements/${editing!.id}`, { method: "PATCH", json: { ...p, active: p.active === "true", position: editing!.position } });
          toast("Saved");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- employee: my travel */

export function MyTravel() {
  const q = useApi<{ flights: Flight[]; hotels: Hotel[]; documents: Doc[] }>("/api/v1/travel/me");
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Home", href: "/me" }, { label: "My travel" }]} />
      <h1 className="text-[24px] font-bold tracking-[-0.02em] sm:text-[30px]">My travel</h1>
      <p className="mt-2 text-[15.5px] text-ink-2">Trips Executive Admin booked for you, and your passport and visa dates.</p>
      <div className="mt-8 flex flex-col gap-5">
        {!q.data ? (
          <Panel>
            <SkeletonRows rows={2} />
          </Panel>
        ) : (
          <>
            <Panel title="Trips" meta={`${q.data.flights.length}`}>
              {q.data.flights.length === 0 ? (
                <EmptyState icon={Plane} title="No trips booked" compact />
              ) : (
                <ul className="divide-y divide-line">
                  {q.data.flights.map((f) => (
                    <li key={f.id} className="flex items-center gap-3.5 px-4 py-3.5 sm:px-5">
                      <Plane className="size-5 shrink-0 text-ink-2" strokeWidth={1.6} aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[15px] font-bold">
                          {f.origin} → {f.destination}
                        </span>
                        <span className="block text-[12.5px] text-ink-3">
                          {fmtDate(f.departure_date)}
                          {f.return_date ? ` – ${fmtDate(f.return_date)}` : ""}
                          {f.booking_reference ? ` · PNR ${f.booking_reference}` : ""}
                          {f.airline ? ` · ${f.airline}` : ""}
                        </span>
                      </span>
                      <Pill tone={flightTone(f.status)}>{FLIGHT_LABEL[f.status]}</Pill>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            {q.data.hotels.length > 0 && (
              <Panel title="Hotels">
                <ul className="divide-y divide-line">
                  {q.data.hotels.map((h) => (
                    <li key={h.id} className="px-4 py-3 text-[13.5px] sm:px-5">
                      <span className="font-medium">{h.hotel}</span>, {h.destination}
                      <span className="block text-[12.5px] text-ink-3">
                        {fmtDate(h.check_in)} – {fmtDate(h.check_out)} · {HOTEL_LABEL[h.status]}
                        {h.booking_reference ? ` · ${h.booking_reference}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            {q.data.documents.length > 0 && (
              <Panel title="Passport and visas">
                <DocList docs={q.data.documents} />
              </Panel>
            )}
          </>
        )}
      </div>
    </PageFrame>
  );
}
