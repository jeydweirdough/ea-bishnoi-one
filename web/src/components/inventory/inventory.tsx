"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowUpFromLine,
  PackageMinus,
  Camera,
  Ban,
  Boxes,
  ChevronRight,
  ClipboardList,
  Layers,
  PackageCheck,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  ShoppingCart,
  SlidersHorizontal,
  TriangleAlert,
  Undo2,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { api, fmtDateTime, fmtRelative, invalidate, post, qs, useApi, type ApiError, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { Button, Chip, Input, Select } from "@/components/ui/controls";
import { CountStrip, Dialog, EmptyState, ErrorState, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { peso } from "@/components/fleet/fleet";
import { useRouter } from "next/navigation";
import { ItemThumb, PhotoGallery } from "@/components/ui/photos";
import { ProofSection, type Proof } from "@/components/ui/proof-list";
import { cn } from "@/lib/cn";

type Item = {
  id: number;
  photo: string | null;
  item_code: string;
  name: string;
  category: string;
  brand: string | null;
  model: string | null;
  unit: string;
  location: string;
  on_hand: number;
  reserved: number;
  available: number;
  reorder_level: number;
  reorder_quantity: number;
  unit_cost_php: string | null;
  value_php: string | null;
  supplier: string | null;
  serialized_on_issue: boolean;
  last_counted_on: string | null;
  status: "active" | "discontinued";
  remarks: string | null;
  low: boolean;
  version: number;
};
type Move = { id: number; proofs?: Proof[]; reference: string; kind: string; quantity: number; balance_after: number; issued_to: Person | null; reason: string | null; actor: Person; at: string; request_id: number | null; item?: { id: number; item_code: string; name: string; location: string; unit: string } };
type MoveDetail = Move & { item: { id: number; item_code: string; name: string; location: string; unit: string; photo: string | null }; request: { id: number; reference: string; subject: string } | null; counterpart: { id: number; location: string } | null };
type ItemDetail = Item & { holders: { person: Person; quantity: number }[]; movements: Move[]; reservations: { id: number; quantity: number; request: { id: number; reference: string; subject: string; requester: Person } }[]; other_locations: { id: number; location: string; on_hand: number; available: number }[]; can_adjust: boolean; can_write_off: boolean };
type Options = { categories: string[]; locations: string[]; can_adjust: boolean; can_write_off: boolean };

const KIND_LABEL: Record<string, string> = { stock_in: "Stock in", issue: "Issued", use: "Used", transfer_out: "Transferred out", transfer_in: "Transferred in", return: "Returned", adjustment: "Adjustment", write_off: "Written off", reserve: "Reserved", release: "Released" };
const KIND_ICON: Record<string, LucideIcon> = { stock_in: ArrowDownToLine, issue: ArrowUpFromLine, use: PackageMinus, transfer_out: ArrowLeftRight, transfer_in: ArrowLeftRight, return: Undo2, adjustment: SlidersHorizontal, write_off: Ban };

function itemFields(o?: Options, editing = false): FieldDef[] {
  return [
    { name: "name", label: "Item", required: true, placeholder: "e.g. HP 85A toner" },
    { name: "item_code", label: "Item code", half: true, placeholder: "Automatic", hint: editing ? undefined : "Leave empty to number it automatically" },
    { name: "category", label: "Category", type: "select", options: o?.categories ?? ["Equipment", "Supplies", "Spare Parts", "Consumables"], required: true, half: true },
    { name: "location", label: "Storage location", required: true, half: true, placeholder: "e.g. HQ stockroom" },
    { name: "unit", label: "Unit", required: true, half: true },
    ...(editing ? [] : [{ name: "opening_quantity", label: "Opening quantity", type: "number", half: true } as FieldDef]),
    { name: "reorder_level", label: "Reorder at", type: "number", half: true, hint: "Alert when available falls to this" },
    { name: "reorder_quantity", label: "Reorder quantity", type: "number", more: true, half: true },
    { name: "unit_cost_php", label: "Unit cost", type: "money", more: true, half: true },
    { name: "brand", label: "Brand", more: true, half: true },
    { name: "model", label: "Model", more: true, half: true },
    { name: "supplier", label: "Preferred supplier", more: true, half: true },
    ...(editing ? [{ name: "status", label: "Status", type: "select", more: true, half: true, options: [{ value: "active", label: "Active" }, { value: "discontinued", label: "Discontinued" }] } as FieldDef] : []),
    { name: "remarks", label: "Remarks", type: "textarea", more: true },
  ];
}

function normalize(p: Record<string, unknown>) {
  return { ...p, opening_quantity: p.opening_quantity ?? 0, reorder_level: p.reorder_level ?? 0, reorder_quantity: p.reorder_quantity ?? 0, unit: p.unit ?? "pc", category: p.category ?? "Equipment" };
}

type View = "stock" | "fill" | "counts" | "moves";

export function InventoryPage() {
  const toast = useToast();
  const o = useApi<Options>("/api/v1/inventory/options");
  const [view, setView] = useState<View>("stock");
  const [creating, setCreating] = useState(false);
  return (
    <ModuleShell
      group="assets"
      item="inventory"
      summary="Consumables, supplies and spare equipment counted by quantity. Every item in or out is recorded on its stock card."
      actions={
        <>
          {o.data?.can_adjust && (
            <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
              Add stock item
            </Button>
          )}
          <DataTools dataset="inventory" statuses={[{ value: "active", label: "Active" }, { value: "discontinued", label: "Discontinued" }]} />
        </>
      }
    >
      <div className="no-scrollbar -mx-4 mb-5 flex gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:px-0" role="group" aria-label="View">
        {(
          [
            ["stock", "Stock"],
            ["fill", "Requests to fill"],
            ["counts", "Counts"],
            ["moves", "Movements"],
          ] as const
        ).map(([v, l]) => (
          <Chip key={v} on={view === v} onClick={() => setView(v)}>
            {l}
          </Chip>
        ))}
      </div>
      {view === "stock" && <StockView options={o.data} />}
      {view === "fill" && <FillView />}
      {view === "counts" && <CountsView options={o.data} />}
      {view === "moves" && <MovesView />}
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Add a consumable or stock item"
        description="For things counted by quantity, like bond paper, toner or cleaning supplies. The opening quantity is recorded as the first movement."
        fields={itemFields(o.data)}
        initial={{ category: "Consumables", unit: "pc", opening_quantity: "0", reorder_level: "0" }}
        submitLabel="Add item"
        photos="inventory_item"
        proof={{
          url: (s) => {
            const id = (s as { opening_movement_id?: number | null })?.opening_movement_id;
            return id ? `/api/v1/inventory/movements/${id}/proof` : null;
          },
          when: (v) => Number(v.opening_quantity || 0) > 0,
          title: "Proof of receipt",
          note: "optional · the delivery, DR or receipt",
          label: "Stock in",
        }}
        onSubmit={async (p) => {
          const i = await post<Item>("/api/v1/inventory/items", normalize(p));
          toast(`Added · ${i.item_code} at ${i.location}`);
          invalidate();
          return i;
        }}
      />
    </ModuleShell>
  );
}

function StockView({ options }: { options?: Options }) {
  const toast = useToast();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [location, setLocation] = useState("");
  const [low, setLow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setTerm(q), 250);
    return () => clearTimeout(t);
  }, [q]);
  const data = useApi<{ items: Item[]; total: number; summary: { lines: number; low: number; reserved: number; value_php: string } }>(`/api/v1/inventory/items${qs({ q: term, location, low, page_size: 200 })}`);
  const s = data.data?.summary;
  async function reorder() {
    const ids = (data.data?.items ?? []).filter((i) => i.low).map((i) => i.id);
    if (!ids.length) return;
    try {
      const r = await post<{ request_id: number; reference: string }>("/api/v1/inventory/reorder", { item_ids: ids });
      toast(`Purchase request drafted · ${r.reference}`);
      router.push(`/r/${r.request_id}`);
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <CountStrip
        items={[
          { icon: Layers, label: "Stock lines", value: s?.lines, href: "/assets/inventory" },
          { icon: TriangleAlert, label: "Low stock", value: s?.low, href: "/assets/inventory", danger: true },
          { icon: ClipboardList, label: "Units reserved", value: s?.reserved, href: "/assets/inventory" },
          { icon: Wallet, label: "Stock value (costed lines)", value: s ? (Number(s.value_php) > 0 ? peso(s.value_php) : "–") : undefined, href: "/assets/inventory" },
        ]}
      />
      <Panel>
        <div className="flex flex-col gap-2 border-b border-line p-3 sm:flex-row sm:px-5">
          <label className="relative flex-1">
            <span className="sr-only">Search stock</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
            <Input type="search" placeholder="Search item or code" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <Select aria-label="Location" value={location} onChange={(e) => setLocation(e.target.value)} className="sm:w-[200px]">
            <option value="">All locations</option>
            {options?.locations.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </Select>
          <Chip on={low} onClick={() => setLow((v) => !v)}>
            Low stock
          </Chip>
        </div>
        {low && (data.data?.items.length ?? 0) > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-canvas px-4 py-2.5 text-[13.5px] sm:px-5">
            <span>{data.data!.items.length} line(s) at or below reorder level.</span>
            <Button size="sm" variant="primary" icon={ShoppingCart} onClick={reorder}>
              Create purchase request
            </Button>
          </div>
        )}
        {data.error ? (
          <ErrorState message={data.error.message} onRetry={data.reload} />
        ) : !data.data ? (
          <SkeletonRows />
        ) : data.data.items.length === 0 ? (
          <EmptyState icon={Boxes} title={q || low || location ? "No matching records" : "No stock items yet"} body={q || low || location ? undefined : "Add items, or import your current stock list from Excel."} compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.items.map((i) => (
              <li key={i.id}>
                <Link href={`/stock/${i.id}`} className="group flex items-center gap-3.5 px-4 py-3 hover:bg-canvas sm:gap-4 sm:px-5">
                  <ItemThumb src={i.photo} icon={Boxes} className={i.low ? "border-danger/50 text-danger" : undefined} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-bold">{i.name}</span>
                    <span className="tabular block text-[12.5px] text-ink-3">
                      {i.item_code} · {i.location}
                      {i.reserved ? ` · ${i.reserved} reserved` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className={cn("tabular block text-[17px] font-bold leading-tight", i.low && "text-danger")}>{i.available}</span>
                    <span className="block text-[11.5px] text-ink-3">{i.unit} available</span>
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-mute group-hover:text-ink" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

type FillLine = { id: number; item_name: string; quantity: number; unit: string; covered: number; received: number; reservations: { id: number; quantity: number; status: string; item_id: number }[]; matches: { id: number; item_code: string; name: string; location: string; available: number; unit: string }[] };
type FillRow = { request: { id: number; reference: string; subject: string; requester: Person; status: string }; lines: FillLine[] };

function FillView() {
  const toast = useToast();
  const data = useApi<FillRow[]>("/api/v1/inventory/requests");
  const [pick, setPick] = useState<Record<number, string>>({});
  async function reserve(line: FillLine) {
    const itemId = Number(pick[line.id] ?? line.matches[0]?.id);
    const stock = line.matches.find((m) => m.id === itemId);
    if (!stock) return;
    const qty = Math.min(line.quantity - line.covered, stock.available);
    try {
      await post("/api/v1/inventory/reserve", { request_item_id: line.id, item_id: itemId, quantity: qty });
      toast(`Reserved ${qty} ${line.unit}`);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  async function act(id: number, action: "issue" | "release") {
    try {
      await post(`/api/v1/inventory/reservations/${id}/${action}`);
      toast(action === "issue" ? "Issued — the requester was notified" : "Reservation released");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  if (!data.data) return <Panel><SkeletonRows /></Panel>;
  if (data.data.length === 0) return <Panel><EmptyState icon={PackageCheck} title="No requests to fulfil" body="Approved item requests appear here so you can reserve and issue from stock." compact /></Panel>;
  return (
    <div className="flex flex-col gap-4">
      {data.data.map((r) => (
        <Panel key={r.request.id} title={r.request.subject} meta={r.request.reference}>
          <p className="border-b border-line px-4 py-2 text-[12.5px] text-ink-3 sm:px-5">
            For {r.request.requester.name} ·{" "}
            <Link href={`/r/${r.request.id}`} className="font-medium text-ink-2 hover:underline">
              Open request
            </Link>
          </p>
          <ul className="divide-y divide-line">
            {r.lines.map((l) => {
              const open = l.quantity - l.covered;
              return (
                <li key={l.id} className="flex flex-col gap-2.5 px-4 py-3 sm:px-5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[14px] font-medium">
                      {l.quantity} {l.unit} {l.item_name}
                    </span>
                    <span className="tabular text-[12.5px] text-ink-3">{l.covered}/{l.quantity} covered</span>
                  </div>
                  {l.reservations.filter((x) => x.status === "reserved").map((x) => (
                    <div key={x.id} className="flex flex-wrap items-center gap-2 rounded-[var(--radius-ctl)] bg-canvas px-3 py-2 text-[13px]">
                      <span className="flex-1">{x.quantity} reserved</span>
                      <Button size="sm" variant="primary" icon={ArrowUpFromLine} onClick={() => act(x.id, "issue")}>
                        Issue
                      </Button>
                      <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => act(x.id, "release")}>
                        Release
                      </Button>
                    </div>
                  ))}
                  {open > 0 &&
                    (l.matches.length === 0 ? (
                      <p className="text-[12.5px] text-ink-3">No matching stock line. Record a delivery in Receiving Proof, or add the item to stock.</p>
                    ) : (
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <Select aria-label="Stock line" value={pick[l.id] ?? String(l.matches[0].id)} onChange={(e) => setPick({ ...pick, [l.id]: e.target.value })}>
                          {l.matches.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name} · {m.location} · {m.available} {m.unit} available
                            </option>
                          ))}
                        </Select>
                        <Button size="sm" icon={ClipboardList} onClick={() => reserve(l)} className="shrink-0">
                          Reserve {open}
                        </Button>
                      </div>
                    ))}
                </li>
              );
            })}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

type CountRow = { id: number; reference: string; location: string | null; status: "open" | "submitted" | "posted" | "cancelled"; lines: { item_id: number; item_code: string; name: string; location: string; unit: string; expected: number; counted: number | null }[]; counted: number; total: number; variances: number; variance_value_php: string; started_by: Person; started_at: string };

function CountsView({ options }: { options?: Options }) {
  const toast = useToast();
  const data = useApi<CountRow[]>("/api/v1/inventory/counts");
  const [loc, setLoc] = useState("");
  const [active, setActive] = useState<number | null>(null);
  async function start() {
    try {
      const c = await post<CountRow>("/api/v1/inventory/counts", { location: loc || null });
      toast(`Count started · ${c.reference}`);
      setActive(c.id);
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  const current = data.data?.find((c) => c.id === active);
  if (current) return <CountSheet count={current} canPost={Boolean(options?.can_adjust)} onBack={() => setActive(null)} />;
  return (
    <div className="flex flex-col gap-4">
      <Panel title="Start a physical count">
        <div className="flex flex-col gap-2 p-4 sm:flex-row sm:px-5">
          <Select aria-label="Location to count" value={loc} onChange={(e) => setLoc(e.target.value)}>
            <option value="">All locations</option>
            {options?.locations.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </Select>
          <Button variant="primary" icon={ClipboardList} onClick={start} className="shrink-0">
            Start physical count
          </Button>
        </div>
      </Panel>
      <Panel title="Counts">
        {!data.data ? (
          <SkeletonRows rows={2} />
        ) : data.data.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No counts yet" compact />
        ) : (
          <ul className="divide-y divide-line">
            {data.data.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => setActive(c.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-canvas sm:px-5">
                  <ClipboardList className="size-[18px] shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-medium">
                      {c.reference} · {c.location ?? "All locations"}
                    </span>
                    <span className="block text-[12.5px] text-ink-3">
                      {c.counted}/{c.total} counted · {c.variances} variance{c.variances === 1 ? "" : "s"} · {c.started_by.name} · {fmtRelative(c.started_at)}
                    </span>
                  </span>
                  <span className={cn("text-[12.5px] font-medium", c.status === "submitted" ? "text-ink" : "text-ink-3")}>{c.status === "open" ? "Counting" : c.status === "submitted" ? "Ready to post" : c.status === "posted" ? "Posted" : "Cancelled"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function CountSheet({ count, canPost, onBack }: { count: CountRow; canPost: boolean; onBack: () => void }) {
  const toast = useToast();
  const [values, setValues] = useState<Record<number, string>>(Object.fromEntries(count.lines.map((l) => [l.item_id, l.counted === null ? "" : String(l.counted)])));
  const [busy, setBusy] = useState(false);
  const editable = count.status === "open";
  async function save(then?: "submit") {
    setBusy(true);
    try {
      await api(`/api/v1/inventory/counts/${count.id}`, { method: "PUT", json: { lines: Object.entries(values).map(([id, v]) => ({ item_id: Number(id), counted: v === "" ? null : Number(v) })) } });
      if (then) await post(`/api/v1/inventory/counts/${count.id}/submit`);
      toast(then ? "Submitted for posting" : "Saved");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function act(action: "post" | "cancel") {
    try {
      await post(`/api/v1/inventory/counts/${count.id}/${action}`);
      toast(action === "post" ? "Count posted — stock adjusted" : "Count cancelled");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" icon={Undo2} onClick={onBack} className="-ml-3">
          All counts
        </Button>
        <span className="flex gap-2">
          {editable && (
            <>
              <Button busy={busy} onClick={() => save()}>
                Save
              </Button>
              <Button variant="primary" busy={busy} onClick={() => save("submit")}>
                Submit count
              </Button>
            </>
          )}
          {count.status === "submitted" && canPost && (
            <Button variant="primary" icon={PackageCheck} onClick={() => act("post")}>
              Post adjustments
            </Button>
          )}
          {(count.status === "open" || count.status === "submitted") && (
            <Button variant="ghost" icon={Ban} onClick={() => act("cancel")}>
              Cancel
            </Button>
          )}
        </span>
      </div>
      <Panel title={`${count.reference} · ${count.location ?? "All locations"}`} meta={`${count.variances} variance${count.variances === 1 ? "" : "s"} · ${peso(count.variance_value_php)}`}>
        <ul className="divide-y divide-line">
          {count.lines.map((l) => {
            const v = values[l.item_id];
            const diff = v !== "" && v !== undefined ? Number(v) - l.expected : null;
            return (
              <li key={l.item_id} className="flex items-center gap-3 px-4 py-2.5 sm:px-5">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium">{l.name}</span>
                  <span className="tabular block text-[12px] text-ink-3">
                    {l.item_code} · {l.location}
                    {count.status !== "open" ? ` · system ${l.expected}` : ""}
                  </span>
                </span>
                {count.status !== "open" && diff !== null && diff !== 0 && <span className={cn("tabular text-[12.5px] font-medium", diff < 0 ? "text-danger" : "")}>{diff > 0 ? `+${diff}` : diff}</span>}
                <Input aria-label={`Counted ${l.name}`} inputMode="numeric" disabled={!editable} className="tabular w-[84px] text-right" value={v ?? ""} onChange={(e) => setValues({ ...values, [l.item_id]: e.target.value.replace(/[^0-9]/g, "") })} placeholder="—" />
                <span className="w-9 text-[12px] text-ink-3">{l.unit}</span>
              </li>
            );
          })}
        </ul>
      </Panel>
      <DocumentsPanel relatedType="inventory_count" relatedId={count.id} title="Count sheet" />
    </div>
  );
}

function MovesView() {
  const data = useApi<{ items: Move[] }>("/api/v1/inventory/movements?page_size=100");
  return (
    <Panel title="Stock movements">
      {!data.data ? (
        <SkeletonRows />
      ) : data.data.items.length === 0 ? (
        <EmptyState icon={ArrowLeftRight} title="No movements yet" compact />
      ) : (
        <ul className="divide-y divide-line">
          {data.data.items.map((m) => (
            <MoveRow key={m.id} m={m} showItem />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function MoveRow({ m, showItem }: { m: Move; showItem?: boolean }) {
  const I = KIND_ICON[m.kind] ?? ArrowLeftRight;
  const [open, setOpen] = useState(false);
  const proofs = m.proofs ?? [];
  return (
    <li>
      <button type="button" onClick={() => setOpen(true)} className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-canvas sm:px-5" aria-label={`${KIND_LABEL[m.kind] ?? m.kind} ${m.quantity > 0 ? `+${m.quantity}` : m.quantity}, ${fmtDateTime(m.at)}: open details`}>
        <I className="mt-0.5 size-[18px] shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block text-[14px]">
            <span className="font-medium">{KIND_LABEL[m.kind] ?? m.kind}</span>
            {showItem && m.item ? (
              <span className="text-ink-2">
                {" "}
                · {m.item.name} ({m.item.location})
              </span>
            ) : null}
          </span>
          <span className="block text-[12.5px] text-ink-3">
            {m.actor.name} · {fmtDateTime(m.at)}
            {m.issued_to ? ` · ${m.kind === "return" ? "from" : "to"} ${m.issued_to.name}` : ""}
            {m.reason ? ` · ${m.reason}` : ""}
          </span>
          {proofs.length > 0 && (
            <span className="mt-2 flex flex-wrap items-center gap-1.5">
              {proofs.slice(0, 4).map((p) => (
                // eslint-disable-next-line @next/next/no-img-element -- private API image
                <img key={p.id} src={p.thumb} alt="" loading="lazy" className="size-11 rounded-[6px] border border-line object-cover" />
              ))}
              <span className="inline-flex items-center gap-1 text-[11.5px] text-ink-3">
                <Camera className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                {proofs.length} photo{proofs.length === 1 ? "" : "s"}
              </span>
            </span>
          )}
        </span>
        <span className="shrink-0 text-right">
          <span className={cn("tabular block text-[14px] font-bold", m.quantity < 0 && "text-ink-2")}>{m.quantity > 0 ? `+${m.quantity}` : m.quantity}</span>
          <span className="tabular block text-[11.5px] text-ink-3">bal. {m.balance_after}</span>
        </span>
        <ChevronRight className="mt-0.5 size-4 shrink-0 text-mute" strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && <MovementDialog id={m.id} onClose={() => setOpen(false)} />}
    </li>
  );
}

/** One transaction: what, how many, who, when, the note and request, and its photo proof. */
function MovementDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useApi<MoveDetail>(`/api/v1/inventory/movements/${id}`);
  const m = q.data;
  const label = m ? KIND_LABEL[m.kind] ?? m.kind : "";
  const rows: [string, React.ReactNode][] = m
    ? [
        ["When", fmtDateTime(m.at)],
        ["Recorded by", m.actor.name],
        ...(m.issued_to ? [[m.kind === "return" ? "Returned by" : "Issued to", m.issued_to.name] as [string, React.ReactNode]] : []),
        ["Quantity", `${m.quantity > 0 ? "+" : ""}${m.quantity} ${m.item.unit}`],
        ["Balance after", `${m.balance_after} ${m.item.unit}`],
        ...(m.reason ? [["Note", m.reason] as [string, React.ReactNode]] : []),
        ...(m.request
          ? [["Request", <Link key="r" href={`/r/${m.request.id}`} className="font-medium underline underline-offset-2">{m.request.reference}</Link>] as [string, React.ReactNode]]
          : []),
        ...(m.counterpart
          ? [[m.kind === "transfer_out" ? "To" : "From", <Link key="c" href={`/stock/${m.counterpart.id}`} className="font-medium underline underline-offset-2">{m.counterpart.location}</Link>] as [string, React.ReactNode]]
          : []),
        ["Reference", <span key="ref" className="tabular">{m.reference}</span>],
      ]
    : [];
  return (
    <Dialog
      open
      onClose={onClose}
      wide
      title={m ? `${label} · ${m.quantity > 0 ? "+" : ""}${m.quantity} ${m.item.unit}` : "Transaction"}
      description={m ? `${m.item.name} · ${m.item.location}` : undefined}
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {q.error ? (
        <ErrorState message={q.error.message} />
      ) : !m ? (
        <SkeletonRows rows={3} />
      ) : (
        <div className="flex flex-col gap-5">
          <dl className="divide-y divide-line rounded-[var(--radius-ctl)] border border-line text-[13.5px]">
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 px-3.5 py-2.5">
                <dt className="text-ink-3">{k}</dt>
                <dd className="text-right font-medium">{v}</dd>
              </div>
            ))}
          </dl>
          <section>
            <h3 className="mb-2 text-[14px] font-bold">Photo proof</h3>
            <ProofSection proofs={m.proofs ?? []} addUrl={`/api/v1/inventory/movements/${m.id}/proof`} label={`${label} · ${m.item.name}`} onAdded={q.reload} />
          </section>
        </div>
      )}
    </Dialog>
  );
}

/* ---------------------------------------------------------------- item page */

type MoveKind = "stock_in" | "issue" | "use" | "transfer" | "return" | "adjustment" | "write_off";

/** What the optional photo proof shows, per transaction. */
const PROOF_TEXT: Record<MoveKind, { title: string; note: string }> = {
  stock_in: { title: "Proof of receipt", note: "optional · the delivery, DR or receipt" },
  issue: { title: "Proof of handover", note: "optional · the item with the person receiving it" },
  use: { title: "Photo proof", note: "optional · where it was used" },
  transfer: { title: "Photo proof", note: "optional · the items being moved" },
  return: { title: "Proof of return", note: "optional · what came back and its condition" },
  adjustment: { title: "Photo proof", note: "optional · what was found" },
  write_off: { title: "Photo proof", note: "optional · the damage, loss or expiry" },
};

export function StockItemView({ id }: { id: number }) {
  const toast = useToast();
  const o = useApi<Options>("/api/v1/inventory/options");
  const q = useApi<ItemDetail>(`/api/v1/inventory/items/${id}`);
  const [dialog, setDialog] = useState<MoveKind | "edit" | null>(null);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This stock line doesn't exist or isn't in your companies." : q.error.message} /></PageFrame>;
  const i = q.data;
  if (!i) return <PageFrame><SkeletonRows /></PageFrame>;
  const moveSpec: Record<MoveKind, { title: string; fields: FieldDef[]; label: string }> = {
    stock_in: { title: "Receive stock", label: "Add to stock", fields: [{ name: "quantity", label: "Quantity", type: "number", required: true, half: true }, { name: "reason", label: "Reference / note", half: true, placeholder: "DR or PO number" }] },
    issue: { title: "Issue stock", label: "Issue", fields: [{ name: "issued_to_id", label: "Issue to", type: "person", required: true, placeholder: "Choose a person" }, { name: "quantity", label: "Quantity", type: "number", required: true, half: true, hint: `${i.available} available` }, { name: "reason", label: "Note", half: true }] },
    use: { title: "Record use", label: "Record use", fields: [{ name: "quantity", label: "Quantity used", type: "number", required: true, half: true, hint: `${i.available} available` }, { name: "reason", label: "Used for", required: true, half: true, placeholder: "e.g. Pantry, printing, cleaning" }] },
    transfer: { title: "Transfer to another location", label: "Transfer", fields: [{ name: "to_location", label: "To location", required: true, half: true }, { name: "quantity", label: "Quantity", type: "number", required: true, half: true }, { name: "reason", label: "Note" }] },
    return: {
      title: "Return to stock",
      label: "Return",
      fields: [
        {
          name: "returned_by", label: "Returned by", type: "select", required: true,
          options: [...i.holders.map((h) => ({ value: String(h.person.id), label: `${h.person.name} · has ${h.quantity} ${i.unit}` })), { value: "other", label: i.holders.length ? "Someone else…" : "Choose a person…" }],
        },
        { name: "issued_to_id", label: "Who returned it?", type: "person", required: true, placeholder: "Choose a person", show: (v) => v.returned_by === "other" },
        { name: "quantity", label: "Quantity", type: "number", required: true, half: true },
        { name: "reason", label: "Note", half: true },
      ],
    },
    adjustment: { title: "Adjust count", label: "Adjust", fields: [{ name: "direction", label: "Direction", type: "select", required: true, half: true, options: [{ value: "add", label: "Add" }, { value: "remove", label: "Remove" }] }, { name: "quantity", label: "Quantity", type: "number", required: true, half: true }, { name: "reason", label: "Reason", type: "textarea", required: true }] },
    write_off: { title: "Write off", label: "Write off", fields: [{ name: "quantity", label: "Quantity", type: "number", required: true, half: true }, { name: "reason", label: "Reason (damaged, lost, expired…)", type: "textarea", required: true }] },
  };
  const actions: [MoveKind, LucideIcon, string, boolean][] = [
    ["issue", ArrowUpFromLine, "Issue", true],
    ["use", PackageMinus, "Record use", true],
    ["stock_in", ArrowDownToLine, "Receive", true],
    ["transfer", ArrowLeftRight, "Transfer", true],
    ["return", Undo2, "Return", true],
    ["adjustment", SlidersHorizontal, "Adjust", i.can_adjust],
    ["write_off", Ban, "Write off", i.can_write_off],
  ];
  const ef = itemFields(o.data, true);
  const spec = dialog && dialog !== "edit" ? moveSpec[dialog] : undefined;
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Consumables & Stock", href: "/assets/inventory" }, { label: i.item_code }]} />
      <header className="flex items-start gap-4">
        <span className="hidden size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet sm:flex" aria-hidden="true">
          <Boxes className="size-6" strokeWidth={1.6} />
        </span>
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ink-3">
            {i.item_code} · {i.category} · {i.location}
          </p>
          <h1 className="mt-1 text-[24px] font-bold leading-tight tracking-[-0.02em] sm:text-[30px]">{i.name}</h1>
          {i.status === "discontinued" && <p className="mt-2 text-[13px] font-medium text-ink-3">Discontinued</p>}
        </div>
      </header>
      <dl className="mt-6 grid grid-cols-2 overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet sm:grid-cols-4 sm:divide-x sm:divide-line">
        {[
          ["Available", i.available, i.low],
          ["On hand", i.on_hand, false],
          ["Reserved", i.reserved, false],
          ["Reorder at", i.reorder_level, false],
        ].map(([k, v, warn], n) => (
          <div key={k as string} className={cn("px-4 py-3.5", n % 2 === 1 && "border-l border-line sm:border-l-0", n > 1 && "border-t border-line sm:border-t-0")}>
            <dt className="text-[12.5px] text-ink-3">{k as string}</dt>
            <dd className={cn("tabular text-[22px] font-bold", !!warn && "text-danger")}>
              {v as number} <span className="text-[12.5px] font-normal text-ink-3">{i.unit}</span>
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 flex flex-wrap gap-2">
        {actions
          .filter(([, , , ok]) => ok)
          .map(([k, I, label], n) => (
            <Button key={k} variant={n === 0 ? "primary" : "secondary"} icon={I} onClick={() => setDialog(k)}>
              {label}
            </Button>
          ))}
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {/* Photos first on phones; top of the right column on desktop. */}
        <div className="lg:col-start-2 lg:row-start-1">
          <PhotoGallery ownerType="inventory_item" ownerId={i.id} canEdit onChange={q.reload} />
        </div>
        <div className="flex min-w-0 flex-col gap-5 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          {i.reservations.length > 0 && (
            <Panel title="Reserved for requests">
              <ul className="divide-y divide-line">
                {i.reservations.map((r) => (
                  <li key={r.id} className="px-4 py-3 text-[13.5px] sm:px-5">
                    <Link href={`/r/${r.request.id}`} className="font-medium hover:underline">
                      {r.quantity} {i.unit} · {r.request.reference}
                    </Link>
                    <span className="block text-[12.5px] text-ink-3">
                      {r.request.subject} · {r.request.requester.name}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Stock card" meta={`${i.movements.filter((m) => !["reserve", "release"].includes(m.kind)).length}`}>
            {i.movements.length === 0 ? (
              <EmptyState icon={ArrowLeftRight} title="No movements yet" compact />
            ) : (
              <ul className="divide-y divide-line">
                {i.movements.filter((m) => !["reserve", "release"].includes(m.kind)).map((m) => (
                  <MoveRow key={m.id} m={m} />
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <aside className="flex flex-col gap-5 lg:col-start-2">
          <Panel title="Information" actions={i.can_adjust ? <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog("edit")}>Edit</Button> : undefined}>
            <dl className="divide-y divide-line text-[13.5px]">
              {[
                ["Brand / model", [i.brand, i.model].filter(Boolean).join(" ")],
                ["Unit cost", i.unit_cost_php ? peso(i.unit_cost_php) : ""],
                ["Value", i.unit_cost_php ? peso(i.value_php) : "No unit cost"],
                ["Supplier", i.supplier ?? ""],
                ["Reorder quantity", i.reorder_quantity ? `${i.reorder_quantity} ${i.unit}` : ""],
                ["Last counted", i.last_counted_on ?? ""],
              ]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 px-4 py-2.5 sm:px-5">
                    <dt className="text-ink-3">{k}</dt>
                    <dd className="text-right font-medium">{v}</dd>
                  </div>
                ))}
            </dl>
          </Panel>
          {i.other_locations.length > 0 && (
            <Panel title="Other locations">
              <ul className="divide-y divide-line">
                {i.other_locations.map((l) => (
                  <li key={l.id}>
                    <Link href={`/stock/${l.id}`} className="flex justify-between px-4 py-2.5 text-[13.5px] hover:bg-canvas sm:px-5">
                      <span>{l.location}</span>
                      <span className="tabular font-medium">{l.available} available</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <DocumentsPanel relatedType="inventory_item" relatedId={i.id} />
        </aside>
      </div>
      <RecordDialog
        open={Boolean(spec)}
        onClose={() => setDialog(null)}
        title={spec?.title ?? ""}
        description={`${i.name} · ${i.location}`}
        fields={spec?.fields ?? []}
        initial={dialog === "adjustment" ? { direction: "add" } : dialog === "return" ? { returned_by: i.holders.length ? String(i.holders[0].person.id) : "other" } : undefined}
        submitLabel={spec?.label}
        proof={
          dialog && dialog !== "edit"
            ? {
                url: (s) => {
                  const mid = (s as ItemDetail).movements[0]?.id;
                  return mid ? `/api/v1/inventory/movements/${mid}/proof` : null;
                },
                ...PROOF_TEXT[dialog],
                label: `${spec?.label ?? ""} · ${i.name}`,
              }
            : undefined
        }
        onSubmit={async (p) => {
          const { returned_by, ...rest } = p;
          if (dialog === "return" && returned_by !== "other") rest.issued_to_id = Number(returned_by);
          const res = await post<ItemDetail>(`/api/v1/inventory/items/${i.id}/move`, { ...rest, kind: dialog });
          q.setData(res);
          toast(`${spec!.label} · ${res.on_hand} ${res.unit} on hand`);
          invalidate();
          return res;
        }}
      />
      <RecordDialog
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        title="Edit stock item"
        fields={ef}
        initial={fromRecord(ef, i as unknown as Record<string, unknown>)}
        onSubmit={async (p) => {
          await api(`/api/v1/inventory/items/${i.id}`, { method: "PATCH", json: { ...normalize(p), version: i.version } });
          toast("Saved");
          q.reload();
        }}
      />
    </PageFrame>
  );
}
