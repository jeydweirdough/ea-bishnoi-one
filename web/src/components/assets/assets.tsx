"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  FileText,
  Archive,
  ArrowLeftRight,
  CircleCheck,
  ClipboardCheck,
  Package,
  PackageCheck,
  Pencil,
  Plus,
  Printer,
  Search,
  Undo2,
  UserCheck,
  UserPlus,
  Wrench,
  ChevronRight,
  Paperclip,
  Download,
  type LucideIcon,
} from "lucide-react";
import { api, fmtDate, fmtRelative, fmtSize, invalidate, post, qs, useApi, ApiError, type Attachment, type Page, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Chip, Field, Input, Select, Textarea, buttonClass } from "@/components/ui/controls";
import { CountStrip, Dialog, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { useShell } from "@/components/shell/shell-context";
import { ItemThumb, PhotoGallery } from "@/components/ui/photos";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- types */

export type AssetStatus = "in_stock" | "assigned" | "under_repair" | "retired";
export type Asset = {
  id: number;
  photo: string | null;
  reference: string;
  name: string;
  category: string;
  serial_number: string | null;
  brand: string | null;
  model: string | null;
  quantity: number;
  unit: string;
  condition: string;
  status: AssetStatus;
  location: string | null;
  company: { id: number; code: string; name: string };
  department: { id: number; name: string } | null;
  holder: Person | null;
  issued_by: Person | null;
  date_issued: string | null;
  acknowledged_at: string | null;
  awaiting_acknowledgement: boolean;
  purchase_date: string | null;
  purchase_reference: string | null;
  description: string | null;
  purpose: string | null;
  remarks: string | null;
  request_id: number | null;
  updated_at: string;
  version: number;
};
type AssetEvent = { id: number; type: string; message: string | null; actor: Person | null; from_holder: Person | null; to_holder: Person | null; at: string };
type Repair = {
  id: number;
  reference: string;
  asset: { id: number; reference: string; name: string; serial_number: string | null };
  issue: string;
  provider: string | null;
  cost_php: string | null;
  status: "open" | "in_repair" | "completed" | "cancelled";
  outcome_condition: string | null;
  notes: string | null;
  opened_by: Person;
  opened_at: string;
  completed_at: string | null;
};
type AssetDetail = Asset & { events: AssetEvent[]; repairs: Repair[]; attachments: Attachment[]; actions: string[] };
type AssetPage = Page<Asset> & { summary: Record<string, number> };

/* ---------------------------------------------------------------- vocabulary */

export const CONDITIONS = [
  { value: "brand_new", label: "Brand new" },
  { value: "used", label: "Used" },
  { value: "for_repair", label: "For repair" },
  { value: "damaged", label: "Damaged" },
  { value: "unserviceable", label: "Unserviceable" },
];
const conditionLabel = (c: string) => CONDITIONS.find((x) => x.value === c)?.label ?? c;
const CATEGORIES = ["IT equipment", "Office equipment", "Furniture", "Appliance", "Mobile device", "Tools", "Other"];

const STATUS: Record<AssetStatus, { label: string; icon: LucideIcon }> = {
  in_stock: { label: "In stock", icon: Package },
  assigned: { label: "Issued", icon: UserCheck },
  under_repair: { label: "Under repair", icon: Wrench },
  retired: { label: "Retired", icon: Archive },
};

export function AssetStatusBadge({ a }: { a: Pick<Asset, "status" | "awaiting_acknowledgement"> }) {
  const s = STATUS[a.status];
  if (a.status === "assigned" && a.awaiting_acknowledgement)
    return (
      <span className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-ink bg-sheet pl-2 pr-2.5 text-[12.5px] font-medium whitespace-nowrap">
        <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" />
        Awaiting acknowledgement
      </span>
    );
  return (
    <span className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border pl-2 pr-2.5 text-[12.5px] font-medium whitespace-nowrap", a.status === "retired" ? "border-line bg-canvas text-ink-3" : "border-edge bg-sheet")}>
      <s.icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
      {s.label}
    </span>
  );
}

const ASSET_FIELDS: FieldDef[] = [
  { name: "name", label: "Asset name", required: true, placeholder: "e.g. Lenovo ThinkPad T14" },
  { name: "category", label: "Category", type: "select", options: CATEGORIES, required: true, half: true },
  { name: "serial_number", label: "Serial number", half: true, hint: "Each serial is one record" },
  { name: "brand", label: "Brand", half: true },
  { name: "model", label: "Model", half: true },
  { name: "condition", label: "Condition", type: "select", options: CONDITIONS, required: true, half: true },
  { name: "location", label: "Location", half: true, placeholder: "Floor, room or site" },
  { name: "department_id", label: "Department", type: "department", more: true, half: true },
  { name: "quantity", label: "Quantity", type: "number", more: true, half: true, hint: "Only for non-serialized items" },
  { name: "unit", label: "Unit", more: true, half: true },
  { name: "purchase_date", label: "Purchase date", type: "date", more: true, half: true },
  { name: "purchase_reference", label: "Purchase reference", more: true, half: true, placeholder: "PO / OR / DR number" },
  { name: "description", label: "Description", type: "textarea", more: true },
  { name: "purpose", label: "Purpose", type: "textarea", more: true },
  { name: "remarks", label: "Remarks", type: "textarea", more: true },
];

/* ---------------------------------------------------------------- shared rows */

function AssetRow({ a, extra }: { a: Asset; extra?: React.ReactNode }) {
  return (
    <li>
      <Link href={`/asset/${a.id}`} className="group flex items-start gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5">
        <ItemThumb src={a.photo} icon={Package} className="mt-0.5 sm:mt-0" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold leading-snug">{a.name}</span>
          <span className="mt-0.5 flex flex-wrap gap-x-2 text-[12.5px] text-ink-3">
            <span className="tabular">{a.reference}</span>
            {a.serial_number && <span className="tabular">SN {a.serial_number}</span>}
            <span>{a.category}</span>
          </span>
          <span className="mt-0.5 block text-[12.5px] text-ink-2">{a.holder ? `With ${a.holder.name}` : a.location ? `At ${a.location}` : "Not issued"}</span>
          {extra}
          <span className="mt-2 flex sm:hidden">
            <AssetStatusBadge a={a} />
          </span>
        </span>
        <span className="hidden sm:block">
          <AssetStatusBadge a={a} />
        </span>
        <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
      </Link>
    </li>
  );
}

function useDebounced(v: string, ms = 250) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

function SearchBox({ value, onChange, placeholder = "Search" }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="relative block flex-1">
      <span className="sr-only">{placeholder}</span>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
      <Input type="search" placeholder={placeholder} className="pl-9" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/* ---------------------------------------------------------------- registry */

/** Filters on the register. "unacknowledged" is a holder filter; the rest are asset statuses. */
const VIEWS: { value: string | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "in_stock", label: "In stock" },
  { value: "assigned", label: "Issued" },
  { value: "unacknowledged", label: "Not yet acknowledged" },
  { value: "under_repair", label: "Under repair" },
  { value: "retired", label: "Retired" },
];

export function AssetRegistry({ view }: { view?: "assigned" | "under_repair" }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const term = useDebounced(q);
  const [status, setStatus] = useState<string | undefined>(view);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const data = useApi<AssetPage>(`/api/v1/assets${qs({ q: term, status: status && status !== "unacknowledged" ? [status] : undefined, holder: status === "unacknowledged" ? status : undefined, page, page_size: 25 })}`);
  const s = data.data?.summary;
  return (
    <ModuleShell
      group="assets"
      item="registry"
      actions={
        <>
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Register asset
          </Button>
          <DataTools dataset="assets" statuses={Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label }))} />
        </>
      }
    >
      <CountStrip
        items={[
          { icon: Package, label: "In stock", value: s?.in_stock, href: "/assets/registry" },
          { icon: UserCheck, label: "Issued", value: s?.assigned, href: "/assets/assignment" },
          { icon: Wrench, label: "Under repair", value: s?.under_repair, href: "/assets/repairs" },
          { icon: ClipboardCheck, label: "Not yet acknowledged", value: s?.unacknowledged, href: "/assets/assignment" },
        ]}
      />
      <div className="mt-5">
        <Panel>
          <div className="flex flex-col gap-3 border-b border-line p-3 sm:px-5">
            <SearchBox value={q} onChange={(v) => (setQ(v), setPage(1))} placeholder="Search name, serial, tag or holder" />
            <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0">
              {VIEWS.map((v) => (
                <Chip key={v.label} on={status === v.value} onClick={() => (setStatus(v.value), setPage(1))}>
                  {v.label}
                </Chip>
              ))}
            </div>
          </div>
          {data.error ? (
            <ErrorState message={data.error.message} onRetry={data.reload} />
          ) : !data.data ? (
            <SkeletonRows />
          ) : data.data.items.length === 0 ? (
            <EmptyState
              icon={Package}
              title={q || status ? "No matching records" : "No assets yet"}
              body={q || status ? "Try another search or status." : "Register equipment here, or record a delivery in Receiving Proof to register it from a request."}
              compact
            />
          ) : (
            <>
              <ul className="divide-y divide-line">
                {data.data.items.map((a) => (
                  <AssetRow key={a.id} a={a} />
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
        title="Register an asset"
        description="Serialized equipment gets one record per serial number."
        fields={ASSET_FIELDS}
        initial={{ condition: "brand_new", quantity: "1", unit: "unit" }}
        submitLabel="Register"
        photos="asset"
        onSubmit={async (p) => {
          const a = await post<Asset>("/api/v1/assets", { ...p, quantity: p.quantity ?? 1, unit: p.unit ?? "unit" });
          toast(`Registered · ${a.reference}`);
          invalidate();
          return a;
        }}
      />
    </ModuleShell>
  );
}

const REPAIR_LABEL: Record<Repair["status"], string> = { open: "Open", in_repair: "At the repair shop", completed: "Completed", cancelled: "Cancelled" };

const REPAIR_FIELDS: FieldDef[] = [
  { name: "status", label: "Status", type: "select", required: true, options: [{ value: "in_repair", label: "At the repair shop" }, { value: "completed", label: "Completed" }, { value: "cancelled", label: "Cancelled" }], half: true },
  { name: "outcome_condition", label: "Condition after repair", type: "select", options: CONDITIONS, half: true, hint: "Required to complete" },
  { name: "provider", label: "Repair provider", half: true },
  { name: "cost_php", label: "Cost", type: "money", half: true },
  { name: "notes", label: "Notes", type: "textarea" },
];

/* ---------------------------------------------------------------- receiving */

type Pending = {
  request: { id: number; reference: string; subject: string; needed_by: string | null; requester: Person };
  items: { id: number; item_name: string; brand: string | null; model: string | null; quantity: number; received_quantity: number; unit: string; item_category: string | null }[];
};
type ReceiptOut = { id: number; reference: string; request: { id: number; reference: string; subject?: string }; received_by: Person; received_on: string; delivery_reference: string | null; supplier: string | null; lines: { item_name: string; quantity: number; unit: string; assets: { id: number; reference: string; serial_number: string | null }[] }[] };

export function ReceivingProof() {
  const pending = useApi<Pending[]>("/api/v1/receiving/pending");
  const receipts = useApi<Page<ReceiptOut>>("/api/v1/receiving?page_size=10");
  const [open, setOpen] = useState<Pending | null>(null);
  return (
    <ModuleShell group="assets" item="receiving-proof" summary="Record what was delivered against an approved request. Equipment can be registered as assets in the same step.">
      <div className="flex flex-col gap-5">
        <Panel title="Waiting for delivery" meta={pending.data ? `${pending.data.length}` : undefined}>
          {!pending.data ? (
            <SkeletonRows rows={2} />
          ) : pending.data.length === 0 ? (
            <EmptyState icon={PackageCheck} title="No pending deliveries" body="Approved item requests appear here until everything is received." compact />
          ) : (
            <ul className="divide-y divide-line">
              {pending.data.map((p) => {
                const left = p.items.reduce((n, i) => n + (i.quantity - i.received_quantity), 0);
                return (
                  <li key={p.request.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                    <Link href={`/r/${p.request.id}`} className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-bold">{p.request.subject}</span>
                      <span className="block text-[12.5px] text-ink-3">
                        <span className="tabular">{p.request.reference}</span> · {p.request.requester.name} · {left} still expected
                        {p.request.needed_by ? ` · needed ${fmtDate(p.request.needed_by)}` : ""}
                      </span>
                    </Link>
                    <Button size="sm" variant="primary" icon={PackageCheck} onClick={() => setOpen(p)} className="self-start sm:self-center">
                      Record delivery
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
        <Panel title="Recent receipts">
          {!receipts.data ? (
            <SkeletonRows rows={2} />
          ) : receipts.data.items.length === 0 ? (
            <EmptyState icon={ClipboardCheck} title="No receipts yet" compact />
          ) : (
            <ul className="divide-y divide-line">
              {receipts.data.items.map((r) => (
                <li key={r.id} className="px-4 py-3 sm:px-5">
                  <p className="text-[14px] font-medium">
                    <span className="tabular">{r.reference}</span> · <Link href={`/r/${r.request.id}`} className="hover:underline">{r.request.reference}</Link>
                  </p>
                  <p className="text-[13px] text-ink-2">{r.lines.map((l) => `${l.quantity} ${l.unit} ${l.item_name}${l.assets.length ? ` (${l.assets.length} registered)` : ""}`).join(", ")}</p>
                  <p className="text-[12px] text-ink-3">
                    {r.received_by.name} · {fmtDate(r.received_on)}
                    {r.delivery_reference ? ` · DR ${r.delivery_reference}` : ""}
                    {r.supplier ? ` · ${r.supplier}` : ""}
                  </p>
                  <ReceivingFormButton receiptId={r.id} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <ReceiveDialog pending={open} onClose={() => setOpen(null)} />
    </ModuleShell>
  );
}

function ReceivingFormButton({ receiptId }: { receiptId: number }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      icon={FileText}
      busy={busy}
      className="mt-2"
      onClick={async () => {
        setBusy(true);
        try {
          const d = await post<{ url: string; control_number: string }>("/api/v1/documents", { template_key: "asset_receiving_form", related_id: receiptId, paper: "A4" });
          toast(`Receiving form · ${d.control_number}`);
          window.open(d.url, "_blank", "noopener");
        } catch (e) {
          toast((e as ApiError).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      Receiving form
    </Button>
  );
}

type LineState = { qty: string; keep: "none" | "asset" | "stock"; stock: string; serials: string; category: string };
type StockOpt = { id: number; item_code: string; name: string; location: string; on_hand: number; unit: string };

function ReceiveDialog({ pending, onClose }: { pending: Pending | null; onClose: () => void }) {
  const toast = useToast();
  const [lines, setLines] = useState<Record<number, LineState>>({});
  const [dr, setDr] = useState("");
  const [supplier, setSupplier] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError>();
  const [seen, setSeen] = useState<Pending | null>(null);
  const stock = useApi<Page<StockOpt>>(pending ? "/api/v1/inventory/items?page_size=500" : null);
  if (pending !== seen) {
    setSeen(pending);
    if (pending) {
      setLines(Object.fromEntries(pending.items.map((i) => [i.id, { qty: String(i.quantity - i.received_quantity), keep: i.item_category === "IT peripherals" || i.item_category === "Equipment" ? "asset" : "none", stock: "", serials: "", category: "" }])));
      setDr("");
      setSupplier("");
      setErr(undefined);
    }
  }
  if (!pending) return null;
  const open = pending.items.filter((i) => i.received_quantity < i.quantity);

  async function save() {
    setBusy(true);
    setErr(undefined);
    try {
      const body = {
        request_id: pending!.request.id,
        delivery_reference: dr || null,
        supplier: supplier || null,
        lines: open
          .filter((i) => Number(lines[i.id]?.qty) > 0)
          .map((i) => ({
            item_id: i.id,
            quantity: Number(lines[i.id].qty),
            register_asset: lines[i.id].keep === "asset",
            inventory_item_id: lines[i.id].keep === "stock" && lines[i.id].stock ? Number(lines[i.id].stock) : null,
            category: lines[i.id].category || null,
            serial_numbers: lines[i.id].keep === "asset" ? lines[i.id].serials.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean) : [],
          })),
      };
      const missing = open.find((i) => Number(lines[i.id]?.qty) > 0 && lines[i.id].keep === "stock" && !lines[i.id].stock);
      if (missing) throw new ApiError(422, `Choose the stock line for ${missing.item_name}.`);
      const r = await post<ReceiptOut>("/api/v1/receiving", body);
      toast(`Received · ${r.reference}`);
      invalidate();
      onClose();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      wide
      title={`Record delivery · ${pending.request.reference}`}
      description={pending.request.subject}
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" icon={PackageCheck} busy={busy} onClick={save}>
            Save receipt
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {open.map((i, idx) => {
          const l: LineState = lines[i.id] ?? { qty: "0", keep: "none", stock: "", serials: "", category: "" };
          const set = (patch: Partial<LineState>) => setLines({ ...lines, [i.id]: { ...l, ...patch } });
          const e = (k: string) => err?.fields[`lines.${idx}.${k}`];
          return (
            <div key={i.id} className="rounded-[var(--radius-ctl)] border border-line p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[14.5px] font-bold">{i.item_name}</p>
                  <p className="text-[12.5px] text-ink-3">
                    {i.received_quantity} of {i.quantity} {i.unit} received{[i.brand, i.model].filter(Boolean).length ? ` · ${[i.brand, i.model].filter(Boolean).join(" ")}` : ""}
                  </p>
                </div>
                <Field label="Received now" htmlFor={`q-${i.id}`} error={e("quantity")} className="w-[110px] shrink-0">
                  <Input id={`q-${i.id}`} inputMode="numeric" className="tabular" value={l.qty} onChange={(ev) => set({ qty: ev.target.value.replace(/[^0-9]/g, "") })} />
                </Field>
              </div>
              <div role="radiogroup" aria-label={`Keep ${i.item_name} as`} className="mt-2 flex flex-wrap gap-1.5">
                {(
                  [
                    ["asset", "Register as assets"],
                    ["stock", "Add to stock"],
                    ["none", "Receive only"],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    role="radio"
                    aria-checked={l.keep === k}
                    onClick={() => set({ keep: k })}
                    className={cn(
                      "min-h-9 rounded-full border px-3 text-[13px] font-medium",
                      l.keep === k ? "border-ink bg-ink text-sheet" : "border-line text-ink-2 hover:border-ink-3",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {l.keep === "stock" && (
                <Field label="Stock line" htmlFor={`st-${i.id}`} error={e("inventory_item_id")} className="mt-2" hint="The received quantity is added to this line's on-hand balance.">
                  <Select id={`st-${i.id}`} value={l.stock} onChange={(ev) => set({ stock: ev.target.value })}>
                    <option value="">Choose…</option>
                    {stock.data?.items.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.item_code} · {o.name} · {o.location} ({o.on_hand} {o.unit})
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {l.keep === "asset" && (
                <div className="mt-2 grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)]">
                  <Field label="Category" htmlFor={`c-${i.id}`} error={e("category")}>
                    <Select id={`c-${i.id}`} value={l.category} onChange={(ev) => set({ category: ev.target.value })}>
                      <option value="">{i.item_category ?? "Choose…"}</option>
                      {CATEGORIES.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Serial numbers" htmlFor={`s-${i.id}`} hint="One per line. Leave empty for non-serialized items." error={e("serial_numbers")}>
                    <Textarea id={`s-${i.id}`} rows={2} value={l.serials} onChange={(ev) => set({ serials: ev.target.value })} />
                  </Field>
                </div>
              )}
            </div>
          );
        })}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Delivery receipt no." htmlFor="dr">
            <Input id="dr" value={dr} onChange={(e) => setDr(e.target.value)} />
          </Field>
          <Field label="Supplier" htmlFor="supplier">
            <Input id="supplier" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
          </Field>
        </div>
        {err && (
          <p role="alert" className="text-[13.5px] text-danger">
            {err.message}
          </p>
        )}
      </div>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- asset page */

const EVENT_LABEL: Record<string, string> = {
  registered: "Registered",
  received: "Received",
  assigned: "Issued",
  acknowledged: "Acknowledged",
  returned: "Returned",
  transferred: "Transferred",
  repair_opened: "Sent for repair",
  repair_closed: "Repair closed",
  updated: "Details edited",
  retired: "Retired",
};

type ActionKey = "edit" | "assign" | "return" | "transfer" | "repair" | "retire";

export function AssetDetailView({ id }: { id: number }) {
  const toast = useToast();
  const { me } = useShell();
  const q = useApi<AssetDetail>(`/api/v1/assets/${id}`);
  const [dialog, setDialog] = useState<ActionKey | null>(null);
  const [repair, setRepair] = useState<Repair | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This asset doesn't exist or isn't shared with you." : q.error.message} /></PageFrame>;
  const a = q.data;
  if (!a) return <PageFrame><SkeletonRows /></PageFrame>;
  const staff = Boolean(me && me.role !== "employee");
  const has = (k: string) => a.actions.includes(k);

  const specs: Record<ActionKey, { title: string; label: string; fields: FieldDef[]; url: string; method?: string; done: string; initial?: Record<string, string> }> = {
    edit: { title: "Edit asset", label: "Save", fields: ASSET_FIELDS, url: `/api/v1/assets/${a.id}`, method: "PATCH", done: "Saved", initial: fromRecord(ASSET_FIELDS, a as unknown as Record<string, unknown>) },
    assign: {
      title: "Issue this asset", label: "Issue", url: `/api/v1/assets/${a.id}/assign`, done: "Issued",
      fields: [
        { name: "employee_id", label: "Issue to", type: "person", required: true, placeholder: "Choose a person" },
        { name: "date_issued", label: "Date issued", type: "date", half: true, more: true },
        { name: "condition", label: "Condition at issue", type: "select", options: CONDITIONS, half: true, more: true },
        { name: "note", label: "Note", type: "textarea", more: true },
      ],
    },
    return: {
      title: "Record return", label: "Record return", url: `/api/v1/assets/${a.id}/return`, done: "Returned", initial: { condition: a.condition },
      fields: [
        { name: "condition", label: "Condition on return", type: "select", options: CONDITIONS, required: true },
        { name: "note", label: "Note", type: "textarea" },
      ],
    },
    transfer: {
      title: "Transfer", label: "Transfer", url: `/api/v1/assets/${a.id}/transfer`, done: "Transferred",
      fields: [
        { name: "employee_id", label: "New holder", type: "person", placeholder: "Keep current holder" },
        { name: "reason", label: "Reason", required: true },
        { name: "department_id", label: "Department", type: "department", more: true, half: true },
        { name: "location", label: "Location", more: true, half: true },
      ],
    },
    repair: {
      title: "Send for repair", label: "Send for repair", url: `/api/v1/assets/${a.id}/repairs`, done: "Sent for repair",
      fields: [
        { name: "issue", label: "What's wrong?", type: "textarea", required: true },
        { name: "provider", label: "Repair provider" },
      ],
    },
    retire: { title: "Retire this asset", label: "Retire", url: `/api/v1/assets/${a.id}/retire`, done: "Retired", fields: [{ name: "reason", label: "Reason", type: "textarea", required: true }] },
  };
  const spec = dialog ? specs[dialog] : undefined;
  const primary: [ActionKey, LucideIcon, string][] = [
    ["assign", UserPlus, "Issue"],
    ["return", Undo2, "Record return"],
    ["transfer", ArrowLeftRight, "Transfer"],
    ["repair", Wrench, "Send for repair"],
  ];

  async function acknowledge() {
    setBusy(true);
    try {
      q.setData(await post<AssetDetail>(`/api/v1/assets/${a!.id}/acknowledge`));
      toast("Receipt acknowledged");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageFrame>
      <Breadcrumbs crumbs={staff ? [{ label: "Asset Management", href: "/assets/registry" }, { label: a.reference }] : [{ label: "My assets", href: "/me/assets" }, { label: a.reference }]} />
      <header className="flex items-start gap-4">
        <ItemThumb src={a.photo} icon={Package} size="lg" className="max-sm:hidden" />
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {a.reference} · {a.category}
            {a.serial_number ? ` · SN ${a.serial_number}` : ""}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">{a.name}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <AssetStatusBadge a={a} />
            <span className="text-[13px] text-ink-2">{conditionLabel(a.condition)}</span>
          </div>
        </div>
      </header>

      {(has("acknowledge") || has("retire") || primary.some(([k]) => has(k))) && (
        <section className="mt-6 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 sm:p-5">
          <p className="text-[15px] font-bold">{has("acknowledge") ? "Receipt confirmation" : a.holder ? `Issued to ${a.holder.name}` : a.status === "under_repair" ? "Out for repair" : "In stock"}</p>
          <p className="mt-1 text-[14px] text-ink-2">
            {has("acknowledge")
              ? `${a.issued_by?.name ?? "Executive Admin"} issued it to you on ${fmtDate(a.date_issued)}.`
              : a.holder
                ? a.acknowledged_at
                  ? `Acknowledged ${fmtDate(a.acknowledged_at)}.`
                  : `Issued ${fmtDate(a.date_issued)} · Receipt not yet acknowledged.`
                : a.location
                  ? `At ${a.location}.`
                  : "Not issued to anyone."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {has("acknowledge") && (
              <Button variant="primary" icon={CircleCheck} busy={busy} onClick={acknowledge}>
                Acknowledge receipt
              </Button>
            )}
            {primary
              .filter(([k]) => has(k))
              .map(([k, I, label], i) => (
                <Button key={k} variant={i === 0 ? "primary" : "secondary"} icon={I} onClick={() => setDialog(k)}>
                  {label}
                </Button>
              ))}
            {a.holder && staff && (
              <Link href={`/print/asset/${a.id}`} target="_blank" className={buttonClass("ghost")}>
                <Printer className="size-4" strokeWidth={1.75} aria-hidden="true" />
                Issuance form
              </Link>
            )}
            {has("retire") && (
              <Button variant="danger" icon={Archive} onClick={() => setDialog("retire")} className="sm:ml-auto">
                Retire asset
              </Button>
            )}
          </div>
        </section>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {/* Photos first on phones; top of the right column on desktop. */}
        <div className="lg:col-start-2 lg:row-start-1">
          <PhotoGallery ownerType="asset" ownerId={a.id} canEdit={staff} />
        </div>
        <div className="flex min-w-0 flex-col gap-5 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <Panel title="History">
            <ol className="px-4 py-4 sm:px-5">
              {a.events.map((e, i) => (
                <li key={e.id} className="relative flex gap-3 pb-4 last:pb-0">
                  {i < a.events.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-line" aria-hidden="true" />}
                  <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full bg-sheet ring-1 ring-edge" aria-hidden="true">
                    <span className="size-1.5 rounded-full bg-ink-3" />
                  </span>
                  <div className="min-w-0 pt-0.5">
                    <p className="text-[13.5px]">
                      <span className="font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>
                      <span className="text-ink-3"> · {e.actor?.name ?? "System"} · {fmtRelative(e.at)}</span>
                    </p>
                    {e.message && <p className="mt-0.5 text-[13.5px] text-ink-2">{e.message}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          {a.repairs.length > 0 && (
            <Panel title="Repairs" meta={`${a.repairs.length}`}>
              <ul className="divide-y divide-line">
                {a.repairs.map((r) => (
                  <li key={r.id} className="flex items-start gap-3 px-4 py-3 sm:px-5">
                    <div className="min-w-0 flex-1">
                      <p className="text-[14px] font-medium">{r.issue}</p>
                      <p className="text-[12.5px] text-ink-3">
                        <span className="tabular">{r.reference}</span> · {REPAIR_LABEL[r.status]}
                        {r.provider ? ` · ${r.provider}` : ""}
                        {r.cost_php ? ` · ₱${Number(r.cost_php).toLocaleString("en-PH", { minimumFractionDigits: 2 })}` : ""}
                      </p>
                    </div>
                    {staff && (r.status === "open" || r.status === "in_repair") && (
                      <Button size="sm" icon={Pencil} onClick={() => setRepair(r)} className="shrink-0">
                        Update repair
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
        <aside className="flex flex-col gap-5 lg:col-start-2">
          <Panel title="Information" actions={has("edit") ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Holder", a.holder?.name ?? "—"],
                ["Department", a.department?.name ?? "—"],
                ["Location", a.location ?? "—"],
                ["Brand / model", [a.brand, a.model].filter(Boolean).join(" ") || "—"],
                ["Quantity", `${a.quantity} ${a.unit}`],
                ["Purchased", a.purchase_date ? `${fmtDate(a.purchase_date)}${a.purchase_reference ? ` · ${a.purchase_reference}` : ""}` : "—"],
                ["Company", a.company.name],
              ]
                .filter(([, v]) => v !== "—")
                .map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="text-right font-medium">{v}</dd>
                </div>
              ))}
              {a.request_id && staff && (
                <div className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                  <dt className="text-ink-3">From request</dt>
                  <dd>
                    <Link href={`/r/${a.request_id}`} className="font-medium hover:underline">
                      Open request
                    </Link>
                  </dd>
                </div>
              )}
            </dl>
          </Panel>
          {staff && <DocumentsPanel relatedType="asset" relatedId={a.id} />}
          <RecordAttachments ownerType="asset" ownerId={a.id} items={a.attachments} canAdd={has("attach")} onChange={q.reload} />
        </aside>
      </div>

      <RecordDialog
        open={Boolean(spec)}
        onClose={() => setDialog(null)}
        title={spec?.title ?? ""}
        fields={spec?.fields ?? []}
        initial={spec?.initial}
        submitLabel={spec?.label}
        onSubmit={async (p) => {
          const body = dialog === "edit" ? { ...p, quantity: p.quantity ?? 1, unit: p.unit ?? "unit", version: a.version } : p;
          const res = await api<AssetDetail | Repair>(spec!.url, { method: spec!.method ?? "POST", json: body });
          if ("actions" in res) q.setData(res);
          else q.reload();
          toast(`${spec!.done} · ${a.reference}`);
          invalidate();
        }}
      />
      <RecordDialog
        open={Boolean(repair)}
        onClose={() => setRepair(null)}
        title={`Update repair · ${repair?.reference ?? ""}`}
        description={a.name}
        fields={REPAIR_FIELDS}
        initial={repair ? { ...fromRecord(REPAIR_FIELDS, repair as unknown as Record<string, unknown>), status: repair.status === "open" ? "in_repair" : "completed" } : undefined}
        onSubmit={async (p) => {
          await api(`/api/v1/asset-repairs/${repair!.id}`, { method: "PATCH", json: p });
          toast("Repair updated");
          q.reload();
          invalidate();
        }}
      />
    </PageFrame>
  );
}

/** Attachment list + upload for any record type the API accepts. */
export function RecordAttachments({ ownerType, ownerId, items, canAdd, onChange }: { ownerType: string; ownerId: number; items: Attachment[]; canAdd: boolean; onChange: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (!items.length && !canAdd) return null;
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.set("owner_type", ownerType);
      fd.set("owner_id", String(ownerId));
      fd.set("file", f);
      try {
        await api("/api/v1/attachments", { method: "POST", body: fd });
      } catch (e) {
        toast(`${f.name}: ${(e as ApiError).message}`, "error");
      }
    }
    setBusy(false);
    onChange();
  }
  return (
    <Panel title="Files" meta={`${items.length}`}>
      {items.length > 0 && (
        <ul className="divide-y divide-line">
          {items.map((x) => (
            <li key={x.id}>
              <a href={x.url} className="flex items-center gap-3 px-4 py-2.5 hover:bg-canvas sm:px-5">
                <Paperclip className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium">{x.filename}</span>
                <span className="tabular text-[12px] text-ink-3">{fmtSize(x.size)}</span>
                <Download className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-label="Download" />
              </a>
            </li>
          ))}
        </ul>
      )}
      {canAdd && (
        <div className={cn("p-3 sm:px-5", items.length > 0 && "border-t border-line")}>
          <label className={cn(buttonClass("ghost", "sm"), "cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60")}>
            <Paperclip className="size-4" strokeWidth={1.75} aria-hidden="true" />
            {busy ? "Uploading…" : "Add a file"}
            <input type="file" multiple className="sr-only" accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,.docx,.xlsx,.csv,.txt" onChange={(e) => (upload(e.target.files), (e.target.value = ""))} />
          </label>
        </div>
      )}
    </Panel>
  );
}

/* ---------------------------------------------------------------- employee: my assets */

export function MyAssets() {
  const toast = useToast();
  const q = useApi<Asset[]>("/api/v1/me/assets");
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Home", href: "/me" }, { label: "My assets" }]} />
      <h1 className="text-[24px] font-bold tracking-[-0.02em] sm:text-[30px]">My assets</h1>
      <p className="mt-2 text-[15.5px] text-ink-2">Equipment issued to you. Confirm anything you&apos;ve received.</p>
      <div className="mt-8">
        <Panel>
          {!q.data ? (
            <SkeletonRows rows={2} />
          ) : q.data.length === 0 ? (
            <EmptyState icon={Package} title="No assets issued to you" compact />
          ) : (
            <ul className="divide-y divide-line">
              {q.data.map((a) => (
                <li key={a.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                  <Link href={`/asset/${a.id}`} className="flex min-w-0 flex-1 items-start gap-3.5">
                    <ItemThumb src={a.photo} icon={Package} size="lg" />
                    <span className="min-w-0">
                      <span className="block truncate text-[15px] font-bold">{a.name}</span>
                      <span className="block text-[12.5px] text-ink-3">
                        <span className="tabular">{a.reference}</span>
                        {a.serial_number ? ` · SN ${a.serial_number}` : ""} · issued {fmtDate(a.date_issued)}
                      </span>
                    </span>
                  </Link>
                  {a.awaiting_acknowledgement ? (
                    <Button
                      size="sm"
                      variant="primary"
                      icon={CircleCheck}
                      onClick={async () => {
                        try {
                          await post(`/api/v1/assets/${a.id}/acknowledge`);
                          toast("Receipt acknowledged");
                          invalidate();
                        } catch (e) {
                          toast((e as ApiError).message, "error");
                        }
                      }}
                      className="self-start sm:self-center"
                    >
                      Acknowledge receipt
                    </Button>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-3">
                      <CircleCheck className="size-4" strokeWidth={1.75} aria-hidden="true" /> Acknowledged
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}
