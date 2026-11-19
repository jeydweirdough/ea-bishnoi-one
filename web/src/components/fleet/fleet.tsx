"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  CalendarClock,
  CarFront,
  Check,
  ChevronRight,
  CircleCheck,
  Fuel,
  Landmark,
  Nfc,
  Pencil,
  Plus,
  RefreshCcw,
  Search,
  Send,
  ShieldCheck,
  TriangleAlert,
  Wrench,
  X,
  Ban,
  type LucideIcon,
} from "lucide-react";
import { api, fmtDate, fmtDateTime, invalidate, post, qs, useApi, type ApiError, type Attachment, type Page, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Chip, Input } from "@/components/ui/controls";
import { CountStrip, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { RecordAttachments } from "@/components/assets/assets";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { useShell } from "@/components/shell/shell-context";
import { ItemThumb, PhotoGallery } from "@/components/ui/photos";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- types */

type VehicleMini = { id: number; reference: string; label: string; plate_number: string | null };
type Vehicle = {
  id: number;
  photo: string | null;
  reference: string;
  label: string;
  company: { id: number; code: string; name: string };
  vehicle_type: string;
  make: string;
  model: string;
  year_model: number | null;
  color: string | null;
  plate_number: string | null;
  conduction_sticker: string | null;
  owner_name: string | null;
  assigned_driver: Person | null;
  registration_renewal_date: string | null;
  insurance_expiry_date: string | null;
  insurer: string | null;
  policy_number: string | null;
  next_pms_date: string | null;
  odometer_km: number | null;
  status: "active" | "under_maintenance" | "inactive" | "disposed";
  notes: string | null;
  due: { registration: number | null; insurance: number | null; pms: number | null };
  version: number;
};
type Service = { id: number; reference: string; vehicle: VehicleMini; kind: "pms" | "repair" | "parts"; status: "scheduled" | "done" | "cancelled"; service_date: string; provider: string | null; description: string; parts: string | null; cost_php: string | null; odometer_km: number | null; next_service_date: string | null; created_by: Person };
type Card = { id: number; reference: string; vehicle: VehicleMini | null; provider: string; card_masked: string; fuel_type: string | null; assigned_user: Person | null; configured_amount_php: string; billing_cycle: string; monitoring_status: string; notes: string | null };
type Rfid = { id: number; vehicle: VehicleMini | null; provider: string; account_reference: string; balance_php: string; low_balance_php: string; low: boolean; monitoring_status: string };
type FinanceReq = { id: number; reference: string; kind: "fleet_billing" | "rfid_reload" | "other"; vehicle: VehicleMini | null; fleet_card: Card | null; rfid_account: Rfid | null; period: string | null; amount_php: string; status: "draft" | "sent" | "paid" | "rejected" | "cancelled"; finance_reference: string | null; notes: string | null; created_by: Person; created_at: string; sent_at: string | null; paid_at: string | null };
type VehicleDetail = Vehicle & {
  services: Service[];
  renewals: { id: number; kind: string; previous_date: string | null; new_date: string; reference: string | null; cost_php: string | null; renewed_by: Person; at: string }[];
  fleet_cards: Card[];
  rfid_accounts: Rfid[];
  attachments: Attachment[];
};
type Options = { vehicle_types: string[]; fuel_types: string[]; rfid_providers: string[]; default_card_limit_php: string };

/* ---------------------------------------------------------------- helpers */

export const peso = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? "—" : `₱${Number(v).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

export function DueLabel({ days, label }: { days: number | null; label?: string }) {
  if (days === null) return <span className="text-ink-3">—</span>;
  const text = days < 0 ? `${-days} days overdue` : days === 0 ? "Due today" : `In ${days} days`;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap", days < 0 ? "font-medium text-danger" : days <= 7 ? "font-medium text-ink" : days <= 30 ? "text-ink-2" : "text-ink-3")}>
      {days <= 7 && <TriangleAlert className="size-3.5" strokeWidth={2} aria-hidden="true" />}
      {label ? `${label} · ` : ""}
      {text}
    </span>
  );
}

const STATUS_LABEL: Record<Vehicle["status"], string> = { active: "Active", under_maintenance: "In the shop", inactive: "Inactive", disposed: "Disposed" };

function soonest(v: Vehicle): { days: number; label: string } | null {
  const xs = ([["Registration", v.due.registration], ["Insurance", v.due.insurance], ["PMS", v.due.pms]] as [string, number | null][]).filter((x): x is [string, number] => x[1] !== null);
  if (!xs.length) return null;
  const [label, days] = xs.sort((a, b) => a[1] - b[1])[0];
  return { label, days };
}

function useOptions() {
  return useApi<Options>("/api/v1/fleet/options");
}

function vehicleFields(o?: Options): FieldDef[] {
  return [
    { name: "plate_number", label: "Plate number", half: true, placeholder: "e.g. NAB 1234", hint: "Or a conduction sticker below" },
    { name: "vehicle_type", label: "Type", type: "select", options: o?.vehicle_types ?? [], required: true, half: true },
    { name: "make", label: "Make", required: true, half: true, placeholder: "e.g. Toyota" },
    { name: "model", label: "Model", required: true, half: true, placeholder: "e.g. Hiace" },
    { name: "registration_renewal_date", label: "Registration renewal", type: "date", half: true },
    { name: "insurance_expiry_date", label: "Insurance expiry", type: "date", half: true },
    { name: "next_pms_date", label: "Next PMS", type: "date", half: true },
    { name: "assigned_driver_id", label: "Assigned driver", type: "person", half: true },
    { name: "conduction_sticker", label: "Conduction sticker", more: true, half: true },
    { name: "year_model", label: "Year model", type: "number", more: true, half: true },
    { name: "color", label: "Color", more: true, half: true },
    { name: "owner_name", label: "Registered owner", more: true, half: true },
    { name: "insurer", label: "Insurer", more: true, half: true },
    { name: "policy_number", label: "Policy number", more: true, half: true },
    { name: "odometer_km", label: "Odometer (km)", type: "number", more: true, half: true },
    { name: "status", label: "Status", type: "select", options: Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })), more: true, half: true },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
}

function VehicleRow({ v, extra }: { v: Vehicle; extra?: React.ReactNode }) {
  const next = soonest(v);
  return (
    <li>
      <Link href={`/vehicle/${v.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <ItemThumb src={v.photo} icon={CarFront} className="mt-0.5 sm:mt-0" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold">
            {v.plate_number ?? v.conduction_sticker} <span className="font-medium text-ink-2">· {v.make} {v.model}</span>
          </span>
          <span className="mt-0.5 block text-[12.5px] text-ink-3">
            {v.vehicle_type}
            {v.assigned_driver ? ` · ${v.assigned_driver.name}` : ""}
            {v.status !== "active" ? ` · ${STATUS_LABEL[v.status]}` : ""}
          </span>
          {extra}
        </span>
        {next && (
          <span className="shrink-0 text-right text-[12.5px]">
            <DueLabel days={next.days} label={next.label} />
          </span>
        )}
        <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}

function useDebounced(v: string) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), 250);
    return () => clearTimeout(t);
  }, [v]);
  return d;
}

/* ---------------------------------------------------------------- vehicles (with "Due soon") */

/**
 * The fleet register. Registration, insurance, PMS, fuel cards and RFID all live on each
 * vehicle's page; this list adds one fleet-wide view on top: what falls due soonest.
 */
export function VehiclesPage({ view = "all" }: { view?: "all" | "due" }) {
  const toast = useToast();
  const o = useOptions();
  const [tab, setTab] = useState(view);
  const [q, setQ] = useState("");
  const term = useDebounced(q);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const data = useApi<Page<Vehicle>>(`/api/v1/fleet/vehicles${qs({ q: term, page, page_size: 25 })}`);
  const due = useApi<{ days: number }[]>("/api/v1/fleet/renewals?within=30");
  const overdue = due.data?.filter((d) => d.days < 0).length;
  const week = due.data?.filter((d) => d.days >= 0 && d.days <= 7).length;
  return (
    <ModuleShell
      group="fleet"
      item="vehicles"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Add vehicle
          </Button>
          <DataTools dataset="vehicles" statuses={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))} />
        </>
      }
    >
      <CountStrip
        items={[
          { icon: CarFront, label: "Vehicles", value: data.data?.total, href: "/fleet/vehicles" },
          { icon: TriangleAlert, label: "Overdue renewals / PMS", value: overdue, href: "/fleet/registration-insurance", danger: true },
          { icon: CalendarClock, label: "Due within 7 days", value: week, href: "/fleet/registration-insurance" },
          { icon: CalendarClock, label: "Due within 30 days", value: due.data?.length, href: "/fleet/registration-insurance" },
        ]}
      />
      <div className="mt-5">
        <Panel>
          <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
            <div className="flex gap-1.5">
              <Chip on={tab === "all"} onClick={() => setTab("all")}>
                All vehicles
              </Chip>
              <Chip on={tab === "due"} onClick={() => setTab("due")} count={due.data?.length || undefined}>
                Due soon
              </Chip>
            </div>
            {tab === "all" && (
              <label className="relative block">
                <span className="sr-only">Search vehicles</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                <Input type="search" placeholder="Search plate, make or model" className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
              </label>
            )}
          </div>
          {tab === "due" ? (
            <DueList />
          ) : data.error ? (
            <ErrorState message={data.error.message} onRetry={data.reload} />
          ) : !data.data ? (
            <SkeletonRows />
          ) : data.data.items.length === 0 ? (
            <EmptyState icon={CarFront} title={q ? "No matching records" : "No vehicles yet"} body={q ? undefined : "Add company vehicles to track registration, insurance and PMS."} compact />
          ) : (
            <>
              <ul className="divide-y divide-line">
                {data.data.items.map((v) => (
                  <VehicleRow key={v.id} v={v} />
                ))}
              </ul>
              <Pager page={page} pageSize={25} total={data.data.total} onPage={setPage} />
            </>
          )}
        </Panel>
      </div>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a vehicle"
        fields={vehicleFields(o.data)}
        initial={{ vehicle_type: "Van", status: "active" }}
        submitLabel="Add vehicle"
        attach={{ ownerType: "vehicle", title: "Attach the OR/CR or registration" }}
        photos="vehicle"
        onSubmit={async (p) => {
          const v = await post<Vehicle>("/api/v1/fleet/vehicles", p);
          toast(`Added · ${v.plate_number ?? v.reference}`);
          invalidate();
          return v;
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- due soon (registration, insurance, PMS) */

type Due = { kind: "registration" | "insurance" | "pms"; date: string; days: number; vehicle: VehicleMini; assigned_driver: Person | null };
const DUE_ICON: Record<Due["kind"], LucideIcon> = { registration: ShieldCheck, insurance: ShieldCheck, pms: Wrench };
const DUE_LABEL: Record<Due["kind"], string> = { registration: "Registration", insurance: "Insurance", pms: "PMS" };

function DueList() {
  const toast = useToast();
  const [within, setWithin] = useState(60);
  const data = useApi<Due[]>(`/api/v1/fleet/renewals?within=${within}`);
  const [renewing, setRenewing] = useState<Due | null>(null);
  const fields: FieldDef[] =
    renewing?.kind === "insurance"
      ? [
          { name: "new_date", label: "New expiry date", type: "date", required: true, half: true },
          { name: "reference", label: "Policy / OR number", half: true },
          { name: "insurer", label: "Insurer", half: true },
          { name: "cost_php", label: "Premium paid", type: "money", half: true },
        ]
      : renewing?.kind === "pms"
        ? SERVICE_FIELDS.filter((f) => f.name !== "vehicle_id")
        : [
            { name: "new_date", label: "Next renewal date", type: "date", required: true, half: true },
            { name: "reference", label: "OR / CR number", half: true },
            { name: "cost_php", label: "Fees paid", type: "money", half: true },
          ];
  return (
    <>
      <div className="flex items-center gap-1.5 border-b border-line px-3 py-2.5 sm:px-5">
        <span className="mr-1 text-[12.5px] text-ink-3">Registration, insurance and PMS in the</span>
        {[30, 60, 120].map((n) => (
          <Chip key={n} on={within === n} onClick={() => setWithin(n)}>
            Next {n} days
          </Chip>
        ))}
      </div>
      {!data.data ? (
        <SkeletonRows />
      ) : data.data.length === 0 ? (
        <EmptyState icon={CircleCheck} title="No upcoming due dates" body={`No registration, insurance or PMS dates in the next ${within} days.`} compact />
      ) : (
        <ul className="divide-y divide-line">
          {data.data.map((d) => {
            const I = DUE_ICON[d.kind];
            return (
              <li key={`${d.kind}-${d.vehicle.id}`} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                <Link href={`/vehicle/${d.vehicle.id}`} className="flex min-w-0 flex-1 items-start gap-3.5">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-line" aria-hidden="true">
                    <I className="size-5" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[15px] font-bold">
                      {DUE_LABEL[d.kind]} · {d.vehicle.label}
                    </span>
                    <span className="block text-[12.5px]">
                      <DueLabel days={d.days} /> <span className="text-ink-3">· {fmtDate(d.date)}</span>
                    </span>
                  </span>
                </Link>
                <Button size="sm" icon={d.kind === "pms" ? Wrench : RefreshCcw} onClick={() => setRenewing(d)} className="self-start sm:self-center">
                  {d.kind === "pms" ? "Log PMS" : "Record renewal"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <RecordDialog
        open={Boolean(renewing)}
        onClose={() => setRenewing(null)}
        title={renewing?.kind === "pms" ? "Log a service" : `Record ${renewing ? DUE_LABEL[renewing.kind].toLowerCase() : ""} renewal`}
        description={renewing?.vehicle.label}
        fields={fields}
        initial={renewing?.kind === "pms" ? { kind: "pms", status: "done", service_date: new Date().toISOString().slice(0, 10) } : undefined}
        submitLabel={renewing?.kind === "pms" ? "Save" : "Save renewal"}
        attach={renewing && renewing.kind !== "pms" ? { ownerType: "vehicle", ownerId: renewing.vehicle.id, title: "Attach the new OR or policy" } : undefined}
        onSubmit={async (p) => {
          if (renewing!.kind === "pms") {
            await post(`/api/v1/fleet/vehicles/${renewing!.vehicle.id}/services`, p);
            toast("Service logged");
          } else {
            await post(`/api/v1/fleet/vehicles/${renewing!.vehicle.id}/renew`, { ...p, kind: renewing!.kind });
            toast("Renewal recorded");
          }
          invalidate();
        }}
      />
    </>
  );
}

/* ---------------------------------------------------------------- service fields (vehicle page) */

const SERVICE_FIELDS: FieldDef[] = [
  { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
  { name: "kind", label: "Type", type: "select", required: true, half: true, options: [{ value: "pms", label: "PMS" }, { value: "repair", label: "Repair" }, { value: "parts", label: "Parts replacement" }] },
  { name: "status", label: "Status", type: "select", required: true, half: true, options: [{ value: "done", label: "Done" }, { value: "scheduled", label: "Scheduled" }] },
  { name: "description", label: "What was done", required: true, placeholder: "e.g. 20,000 km PMS, change oil and filters" },
  { name: "service_date", label: "Date", type: "date", required: true, half: true },
  { name: "cost_php", label: "Cost", type: "money", half: true },
  { name: "provider", label: "Service provider", more: true, half: true },
  { name: "odometer_km", label: "Odometer (km)", type: "number", more: true, half: true },
  { name: "next_service_date", label: "Next service", type: "date", more: true, half: true, hint: "PMS: updates the vehicle's next PMS date" },
  { name: "parts", label: "Parts replaced", type: "textarea", more: true },
];

/* ---------------------------------------------------------------- fuel cards & RFID (on the vehicle page) */

/**
 * Fuel cards and toll RFID accounts of one vehicle, with every action on them.
 * `vehicle === null` lists the cards and accounts not linked to any vehicle yet (shown on Fuel & Toll Billing).
 */
function FuelAccounts({ vehicle, cards, rfid, onChange }: { vehicle: VehicleMini | null; cards: Card[]; rfid: Rfid[]; onChange: () => void }) {
  const toast = useToast();
  const o = useOptions();
  const [dialog, setDialog] = useState<null | "card" | "rfid">(null);
  const [editing, setEditing] = useState<Card | null>(null);
  const [balance, setBalance] = useState<Rfid | null>(null);
  const [reload, setReload] = useState<Rfid | null>(null);
  const done = (msg: string) => {
    toast(msg);
    invalidate();
    onChange();
  };
  const cardFields: FieldDef[] = [
    { name: "card_number_last4", label: "Last 4 digits of the card", required: true, half: true, placeholder: "1234", hint: "Full card numbers are never stored" },
    { name: "fuel_type", label: "Fuel type", type: "select", options: o.data?.fuel_types ?? [], half: true },
    { name: "configured_amount_php", label: "Monthly limit", type: "money", half: true, hint: `Leave empty for the default ${peso(o.data?.default_card_limit_php)}` },
    { name: "assigned_user_id", label: "Card holder", type: "person", half: true },
    { name: "provider", label: "Provider", more: true, half: true },
    { name: "billing_cycle", label: "Billing cycle", type: "select", more: true, half: true, options: [{ value: "monthly", label: "Monthly" }, { value: "biweekly", label: "Every 2 weeks" }, { value: "weekly", label: "Weekly" }] },
    { name: "notes", label: "Notes", type: "textarea", more: true },
  ];
  const editFields: FieldDef[] = [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle" },
    { name: "assigned_user_id", label: "Card holder", type: "person", half: true },
    { name: "configured_amount_php", label: "Monthly limit", type: "money", half: true },
    { name: "monitoring_status", label: "Status", type: "select", required: true, half: true, options: [{ value: "active", label: "Active" }, { value: "suspended", label: "Suspended" }, { value: "cancelled", label: "Cancelled" }] },
    { name: "fuel_type", label: "Fuel type", type: "select", options: o.data?.fuel_types ?? [], half: true },
    { name: "notes", label: "Notes", type: "textarea" },
  ];
  const empty = cards.length === 0 && rfid.length === 0;
  return (
    <Panel
      title={vehicle ? "Fuel & toll" : "Not linked to a vehicle"}
      actions={
        vehicle ? (
          <span className="flex gap-1">
            <Button size="sm" variant="ghost" icon={Plus} onClick={() => setDialog("card")}>
              Fuel card
            </Button>
            <Button size="sm" variant="ghost" icon={Plus} onClick={() => setDialog("rfid")}>
              RFID
            </Button>
          </span>
        ) : undefined
      }
    >
      {empty ? (
        <p className="px-4 py-3 text-[13px] text-ink-3 sm:px-5">No fuel card or RFID account yet.</p>
      ) : (
        <ul className="divide-y divide-line">
          {cards.map((c) => (
            <li key={`c${c.id}`} className="flex items-start gap-3 px-4 py-3 sm:px-5">
              <Fuel className="mt-0.5 size-[18px] shrink-0 text-ink-2" strokeWidth={1.75} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="tabular block text-[14px] font-bold">
                  {c.provider} {c.card_masked}
                  {c.monitoring_status !== "active" && <span className="ml-1.5 text-[12px] font-medium text-ink-3">{c.monitoring_status === "suspended" ? "Suspended" : "Cancelled"}</span>}
                </span>
                <span className="block text-[12.5px] text-ink-3">
                  {peso(c.configured_amount_php)} {c.billing_cycle}
                  {c.fuel_type ? ` · ${c.fuel_type}` : ""}
                  {c.assigned_user ? ` · ${c.assigned_user.name}` : ""}
                </span>
              </span>
              <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${c.provider} ${c.card_masked}`} onClick={() => setEditing(c)} />
            </li>
          ))}
          {rfid.map((r) => (
            <li key={`r${r.id}`} className="flex items-start gap-3 px-4 py-3 sm:px-5">
              <Nfc className="mt-0.5 size-[18px] shrink-0 text-ink-2" strokeWidth={1.75} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-bold">
                  {r.provider} <span className="tabular font-medium text-ink-2">{r.account_reference}</span>
                </span>
                <span className={cn("tabular block text-[12.5px]", r.low ? "font-medium text-danger" : "text-ink-3")}>
                  Balance {peso(r.balance_php)}
                  {r.low ? " · Low" : ""}
                </span>
                <button type="button" onClick={() => setReload(r)} className="mt-1.5 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink underline-offset-2 hover:underline">
                  <Landmark className="size-3.5" strokeWidth={1.75} aria-hidden="true" /> Request reload
                </button>
              </span>
              <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Update balance of ${r.provider} ${r.account_reference}`} title="Update balance" onClick={() => setBalance(r)} />
            </li>
          ))}
        </ul>
      )}
      <RecordDialog
        open={dialog === "card"}
        onClose={() => setDialog(null)}
        title="Add a fleet card"
        description={vehicle?.label}
        fields={cardFields}
        initial={{ provider: "Shell", billing_cycle: "monthly" }}
        submitLabel="Add card"
        onSubmit={async (p) => {
          await post("/api/v1/fleet/cards", { ...p, vehicle_id: vehicle?.id ?? null, provider: p.provider ?? "Shell", billing_cycle: p.billing_cycle ?? "monthly" });
          done("Fleet card added");
        }}
      />
      <RecordDialog
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.provider ?? ""} ${editing?.card_masked ?? ""}`}
        fields={editFields}
        initial={editing ? fromRecord(editFields, { ...editing, vehicle_id: editing.vehicle?.id, assigned_user_id: editing.assigned_user?.id } as unknown as Record<string, unknown>) : undefined}
        onSubmit={async (p) => {
          await api(`/api/v1/fleet/cards/${editing!.id}`, { method: "PATCH", json: p });
          done("Card updated");
        }}
      />
      <RecordDialog
        open={dialog === "rfid"}
        onClose={() => setDialog(null)}
        title="Add an RFID account"
        description={vehicle?.label}
        fields={[
          { name: "provider", label: "Provider", type: "select", options: o.data?.rfid_providers ?? [], required: true, half: true },
          { name: "account_reference", label: "Account number", required: true, half: true },
          { name: "balance_php", label: "Current balance", type: "money", half: true },
          { name: "low_balance_php", label: "Warn below", type: "money", half: true },
        ]}
        initial={{ provider: "Autosweep", low_balance_php: "500" }}
        submitLabel="Add account"
        onSubmit={async (p) => {
          await post("/api/v1/fleet/rfid", { ...p, vehicle_id: vehicle?.id ?? null, balance_php: p.balance_php ?? "0", low_balance_php: p.low_balance_php ?? "500" });
          done("RFID account added");
        }}
      />
      <RecordDialog
        open={Boolean(balance)}
        onClose={() => setBalance(null)}
        title="Update balance"
        description="Enter the balance shown on the provider's portal."
        fields={[
          { name: "balance_php", label: "Balance", type: "money", required: true },
          { name: "note", label: "Note" },
        ]}
        initial={{ balance_php: balance?.balance_php ?? "" }}
        onSubmit={async (p) => {
          await post(`/api/v1/fleet/rfid/${balance!.id}/balance`, p);
          done("Balance updated");
        }}
      />
      <RecordDialog
        open={Boolean(reload)}
        onClose={() => setReload(null)}
        title="Request a reload from Finance"
        description={reload ? `${reload.provider} ${reload.account_reference}. The balance updates when Finance confirms payment.` : undefined}
        fields={[
          { name: "amount_php", label: "Amount", type: "money", required: true },
          { name: "notes", label: "Note", type: "textarea" },
        ]}
        submitLabel="Send to Finance"
        onSubmit={async (p) => {
          await post("/api/v1/fleet/finance", { ...p, kind: "rfid_reload", rfid_account_id: reload!.id, send: true });
          done("Sent to Finance");
        }}
      />
    </Panel>
  );
}

/* ---------------------------------------------------------------- fuel & monthly billing (Finance hand-offs) */

const FIN_LABEL: Record<FinanceReq["status"], string> = { draft: "Draft", sent: "With Finance", paid: "Paid", rejected: "Rejected", cancelled: "Cancelled" };

export function FuelBillingPage() {
  const toast = useToast();
  const [status, setStatus] = useState<string | undefined>("sent");
  const [page, setPage] = useState(1);
  const data = useApi<Page<FinanceReq>>(`/api/v1/fleet/finance${qs({ status: status ? [status] : undefined, page, page_size: 25 })}`);
  const { me } = useShell();
  const o = useOptions();
  const cards = useApi<Card[]>("/api/v1/fleet/cards");
  const rfid = useApi<Rfid[]>("/api/v1/fleet/rfid");
  const [creating, setCreating] = useState(false);
  const [limitOpen, setLimitOpen] = useState(false);
  const unlinkedCards = (cards.data ?? []).filter((c) => !c.vehicle && c.monitoring_status !== "cancelled");
  const unlinkedRfid = (rfid.data ?? []).filter((r) => !r.vehicle);
  const [acting, setActing] = useState<{ f: FinanceReq; action: "paid" | "reject" | "cancel" } | null>(null);
  const month = new Date().toISOString().slice(0, 7);
  const fields: FieldDef[] = [
    { name: "fleet_card_id", label: "Fleet card", type: "select", required: true, options: (cards.data ?? []).filter((c) => c.monitoring_status === "active").map((c) => ({ value: String(c.id), label: `${c.provider} ${c.card_masked} · ${c.vehicle?.label ?? "no vehicle"}` })) },
    { name: "period", label: "Billing month", required: true, half: true, placeholder: "YYYY-MM" },
    { name: "amount_php", label: "Statement amount", type: "money", required: true, half: true },
    { name: "notes", label: "Note", type: "textarea", more: true },
  ];
  const actionFields: Record<"paid" | "reject" | "cancel", FieldDef[]> = {
    paid: [{ name: "finance_reference", label: "Finance payment reference", required: true, placeholder: "e.g. CV-2026-1188" }],
    reject: [{ name: "reason", label: "Why did Finance reject it?", type: "textarea", required: true }],
    cancel: [{ name: "reason", label: "Reason", type: "textarea", required: true }],
  };
  async function send(f: FinanceReq) {
    try {
      await post(`/api/v1/fleet/finance/${f.id}/send`, {});
      toast(`Sent to Finance · ${f.reference}`);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  return (
    <ModuleShell
      group="fleet"
      item="fuel-billing"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Record card statement
          </Button>
          <DataTools
            dataset="fleet_accounts"
            extra={me?.role === "admin" ? [{ label: "Default card limit", hint: o.data ? `${peso(o.data.default_card_limit_php)} a month for new cards` : undefined, icon: Pencil, onSelect: () => setLimitOpen(true) }] : []}
          />
        </>
      }
    >
      <p className="mb-4 text-[13px] text-ink-3">Fuel cards and RFID accounts are added and managed on each vehicle&rsquo;s page.</p>
      {(unlinkedCards.length > 0 || unlinkedRfid.length > 0) && (
        <div className="mb-5">
          <FuelAccounts vehicle={null} cards={unlinkedCards} rfid={unlinkedRfid} onChange={() => (cards.reload(), rfid.reload())} />
        </div>
      )}
      <Panel>
        <div className="no-scrollbar -mx-0 flex gap-1.5 overflow-x-auto border-b border-line p-3 sm:px-5">
          {[["sent", "With Finance"], ["draft", "Drafts"], ["paid", "Paid"], [undefined, "All"]].map(([v, l]) => (
            <Chip key={l} on={status === v} onClick={() => (setStatus(v), setPage(1))}>
              {l}
            </Chip>
          ))}
        </div>
        {!data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState icon={Landmark} title="No records" body="Card statements and RFID reload requests appear here once recorded." compact />
        ) : (
          <>
            <ul className="divide-y divide-line">
              {data.data.items.map((f) => (
                <li key={f.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                  <span className="flex min-w-0 flex-1 items-start gap-3.5">
                    <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-[10px] border", f.status === "paid" ? "border-ink bg-ink text-white" : "border-line")} aria-hidden="true">
                      {f.kind === "rfid_reload" ? <Nfc className="size-5" strokeWidth={1.6} /> : <Fuel className="size-5" strokeWidth={1.6} />}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[15px] font-bold">
                        <span className="tabular">{peso(f.amount_php)}</span> · {f.kind === "rfid_reload" ? `RFID reload ${f.rfid_account?.provider ?? ""}` : `Fleet card ${f.fleet_card?.card_masked ?? ""}`}
                        {f.period ? ` · ${f.period}` : ""}
                      </span>
                      <span className="block text-[12.5px] text-ink-3">
                        <span className="tabular">{f.reference}</span> · {FIN_LABEL[f.status]}
                        {f.vehicle ? ` · ${f.vehicle.label}` : ""}
                        {f.finance_reference ? ` · Finance ref ${f.finance_reference}` : ""}
                        {f.sent_at && f.status === "sent" ? ` · sent ${fmtDateTime(f.sent_at)}` : ""}
                      </span>
                    </span>
                  </span>
                  <span className="flex flex-wrap gap-2 self-start sm:self-center">
                    {f.status === "draft" && (
                      <Button size="sm" variant="primary" icon={Send} onClick={() => send(f)}>
                        Send to Finance
                      </Button>
                    )}
                    {f.status === "sent" && (
                      <>
                        <Button size="sm" variant="primary" icon={Check} onClick={() => setActing({ f, action: "paid" })}>
                          Record payment
                        </Button>
                        <Button size="sm" variant="ghost" icon={X} onClick={() => setActing({ f, action: "reject" })}>
                          Rejected
                        </Button>
                      </>
                    )}
                    {(f.status === "draft" || f.status === "sent") && (
                      <Button size="sm" variant="ghost" icon={Ban} aria-label="Cancel" onClick={() => setActing({ f, action: "cancel" })}>
                        <span className="sr-only sm:not-sr-only">Cancel</span>
                      </Button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={25} total={data.data.total} onPage={setPage} />
          </>
        )}
      </Panel>
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Record a fleet card statement"
        description="Saved as a draft. Send it to Finance when it's checked."
        fields={fields}
        initial={{ period: month }}
        submitLabel="Save draft"
        onSubmit={async (p) => {
          await post("/api/v1/fleet/finance", { ...p, kind: "fleet_billing" });
          toast("Statement saved");
          setStatus("draft");
          invalidate();
        }}
      />
      <RecordDialog
        open={limitOpen}
        onClose={() => setLimitOpen(false)}
        title="Default monthly limit"
        description="Applied to new cards when no limit is entered. Existing cards keep their own limit."
        fields={[{ name: "amount_php", label: "Amount", type: "money", required: true }]}
        initial={{ amount_php: o.data?.default_card_limit_php ?? "" }}
        onSubmit={async (p) => {
          await api("/api/v1/fleet/settings/default-card-limit", { method: "PUT", json: p });
          toast("Default limit saved");
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(acting)}
        onClose={() => setActing(null)}
        title={acting?.action === "paid" ? "Record Finance payment" : acting?.action === "reject" ? "Record Finance rejection" : "Cancel hand-off"}
        description={acting ? `${acting.f.reference} · ${peso(acting.f.amount_php)}` : undefined}
        fields={acting ? actionFields[acting.action] : []}
        submitLabel={acting?.action === "paid" ? "Record payment" : "Save"}
        onSubmit={async (p) => {
          await post(`/api/v1/fleet/finance/${acting!.f.id}/${acting!.action}`, p);
          toast(acting!.action === "paid" ? "Payment recorded" : "Updated");
          invalidate();
        }}
      />
    </ModuleShell>
  );
}

/* ---------------------------------------------------------------- vehicle page */

export function VehicleDetailView({ id }: { id: number }) {
  const toast = useToast();
  const o = useOptions();
  const q = useApi<VehicleDetail>(`/api/v1/fleet/vehicles/${id}`);
  const [dialog, setDialog] = useState<null | "edit" | "registration" | "insurance" | "service">(null);
  const [completing, setCompleting] = useState<Service | null>(null);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This vehicle doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const v = q.data;
  if (!v) return <PageFrame><SkeletonRows /></PageFrame>;
  const vf = vehicleFields(o.data);
  const renewFields: FieldDef[] = [
    { name: "new_date", label: dialog === "insurance" ? "New expiry date" : "Next renewal date", type: "date", required: true, half: true },
    { name: "reference", label: dialog === "insurance" ? "Policy / OR number" : "OR / CR number", half: true },
    { name: "cost_php", label: "Amount paid", type: "money", half: true },
    ...(dialog === "insurance" ? [{ name: "insurer", label: "Insurer", half: true } as FieldDef] : []),
  ];
  const dates: [string, string | null, number | null, "registration" | "insurance" | "service"][] = [
    ["Registration", v.registration_renewal_date, v.due.registration, "registration"],
    ["Insurance", v.insurance_expiry_date, v.due.insurance, "insurance"],
    ["Next PMS", v.next_pms_date, v.due.pms, "service"],
  ];
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Fleet & Vehicles", href: "/fleet/vehicles" }, { label: v.plate_number ?? v.reference }]} />
      <header className="flex items-start gap-4">
        <ItemThumb src={v.photo} icon={CarFront} size="lg" className="max-sm:hidden" />
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {v.reference} · {v.vehicle_type}
            {v.year_model ? ` · ${v.year_model}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">
            {v.plate_number ?? v.conduction_sticker} · {v.make} {v.model}
          </h1>
          <p className="mt-2 text-[14px] text-ink-2">
            {STATUS_LABEL[v.status]}
            {v.assigned_driver ? ` · Driver ${v.assigned_driver.name}` : ""}
            {v.odometer_km !== null ? ` · ${v.odometer_km.toLocaleString()} km` : ""}
          </p>
        </div>
      </header>

      <ul className="mt-6 grid gap-3 sm:grid-cols-3">
        {dates.map(([label, date, days, action]) => (
          <li key={label} className={cn("rounded-[var(--radius-panel)] border bg-sheet p-4", days !== null && days <= 7 ? "border-ink" : "border-line")}>
            <p className="text-[13px] font-medium text-ink-3">{label}</p>
            <p className="mt-1 text-[16px] font-bold">{fmtDate(date)}</p>
            <p className="mt-0.5 text-[12.5px]">
              <DueLabel days={days} />
            </p>
            <Button size="sm" variant="ghost" icon={action === "service" ? Wrench : RefreshCcw} onClick={() => setDialog(action)} className="-ml-2 mt-2">
              {action === "service" ? "Log PMS" : "Record renewal"}
            </Button>
          </li>
        ))}
      </ul>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {/* Photos first on phones; top of the right column on desktop. */}
        <div className="lg:col-start-2 lg:row-start-1">
          <PhotoGallery ownerType="vehicle" ownerId={v.id} canEdit onChange={q.reload} />
        </div>
        <div className="flex min-w-0 flex-col gap-5 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <Panel title="Service history" meta={`${v.services.length}`}>
            {v.services.length === 0 ? (
              <EmptyState icon={Wrench} title="No services logged" compact />
            ) : (
              <ul className="divide-y divide-line">
                {v.services.map((s) => (
                  <li key={s.id} className="flex items-start gap-3 px-4 py-3 sm:px-5">
                    <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-medium">{s.description}</p>
                    <p className="text-[12.5px] text-ink-3">
                      <span className="tabular">{s.reference}</span> · {s.kind === "pms" ? "PMS" : s.kind === "repair" ? "Repair" : "Parts"} · {s.status === "scheduled" ? "Scheduled " : ""}
                      {fmtDate(s.service_date)}
                      {s.cost_php ? ` · ${peso(s.cost_php)}` : ""}
                      {s.odometer_km ? ` · ${s.odometer_km.toLocaleString()} km` : ""}
                      {s.provider ? ` · ${s.provider}` : ""}
                    </p>
                    </div>
                    {s.status === "scheduled" && (
                      <Button size="sm" icon={Check} onClick={() => setCompleting(s)} className="shrink-0">
                        Mark done
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {v.renewals.length > 0 && (
            <Panel title="Renewals">
              <ul className="divide-y divide-line">
                {v.renewals.map((r) => (
                  <li key={r.id} className="px-4 py-3 text-[13.5px] sm:px-5">
                    <span className="font-medium">{r.kind === "registration" ? "Registration" : "Insurance"}</span> renewed to {fmtDate(r.new_date)}
                    <span className="block text-[12.5px] text-ink-3">
                      {r.reference ? `${r.reference} · ` : ""}
                      {r.cost_php ? `${peso(r.cost_php)} · ` : ""}
                      {r.renewed_by.name} · {fmtDate(r.at)}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
        <aside className="flex flex-col gap-5 lg:col-start-2">
          <Panel title="Information" actions={<Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button>}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Conduction sticker", v.conduction_sticker ?? "—"],
                ["Color", v.color ?? "—"],
                ["Registered owner", v.owner_name ?? "—"],
                ["Insurer", [v.insurer, v.policy_number].filter(Boolean).join(" · ") || "—"],
                ["Company", v.company.name],
              ]
                .filter(([, val]) => val !== "—")
                .map(([k, val]) => (
                <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="text-right font-medium">{val}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <FuelAccounts vehicle={{ id: v.id, reference: v.reference, label: v.label, plate_number: v.plate_number }} cards={v.fleet_cards} rfid={v.rfid_accounts} onChange={q.reload} />
          <DocumentsPanel relatedType="vehicle" relatedId={v.id} />
          <RecordAttachments ownerType="vehicle" ownerId={v.id} items={v.attachments} canAdd onChange={q.reload} />
        </aside>
      </div>

      <RecordDialog
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        title="Edit vehicle"
        fields={vf}
        initial={fromRecord(vf, { ...v, assigned_driver_id: v.assigned_driver?.id } as unknown as Record<string, unknown>)}
        onSubmit={async (p) => {
          q.setData({ ...v, ...(await api<Vehicle>(`/api/v1/fleet/vehicles/${v.id}`, { method: "PATCH", json: { ...p, version: v.version } })) });
          toast("Vehicle saved");
          q.reload();
        }}
      />
      <RecordDialog
        open={dialog === "registration" || dialog === "insurance"}
        onClose={() => setDialog(null)}
        title={dialog === "insurance" ? "Record insurance renewal" : "Record registration renewal"}
        fields={renewFields}
        submitLabel="Save renewal"
        attach={{ ownerType: "vehicle", ownerId: v.id, title: "Attach the new OR or policy" }}
        onSubmit={async (p) => {
          await post(`/api/v1/fleet/vehicles/${v.id}/renew`, { ...p, kind: dialog });
          toast("Renewal recorded");
          q.reload();
          invalidate();
        }}
      />
      <RecordDialog
        open={dialog === "service"}
        onClose={() => setDialog(null)}
        title="Log a service"
        description={v.label}
        fields={SERVICE_FIELDS.filter((f) => f.name !== "vehicle_id")}
        initial={{ kind: "pms", status: "done", service_date: new Date().toISOString().slice(0, 10) }}
        onSubmit={async (p) => {
          await post(`/api/v1/fleet/vehicles/${v.id}/services`, p);
          toast("Service logged");
          q.reload();
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(completing)}
        onClose={() => setCompleting(null)}
        title="Mark service done"
        description={completing ? `${v.label} · ${completing.description}` : undefined}
        fields={[
          { name: "cost_php", label: "Final cost", type: "money", half: true },
          { name: "odometer_km", label: "Odometer (km)", type: "number", half: true },
          { name: "next_service_date", label: "Next service", type: "date", half: true },
          { name: "parts", label: "Parts replaced", type: "textarea" },
        ]}
        submitLabel="Mark done"
        onSubmit={async (p) => {
          await post(`/api/v1/fleet/services/${completing!.id}/complete`, p);
          toast("Service completed");
          q.reload();
          invalidate();
        }}
      />
    </PageFrame>
  );
}

