"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  FileText,
  Archive,
  ArrowLeftRight,
  CircleCheck,
  ClipboardCheck,
  Boxes,
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
  ChevronDown,
  ListChecks,
  ChevronRight,
  Paperclip,
  Download,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { api, fmtDate, fmtDateTime, fmtRelative, fmtSize, invalidate, post, qs, useApi, ApiError, type Attachment, type Page, type Person } from "@/lib/api";
import { Breadcrumbs, PageFrame } from "@/components/page/module-page";
import { ActionRow, Button, Chip, Field, Input, Select, Textarea, buttonClass } from "@/components/ui/controls";
import { ProofSection, type Proof } from "@/components/ui/proof-list";
import { CountStrip, Dialog, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { RecordDialog, fromRecord, type FieldDef } from "@/components/ui/record-form";
import { ModuleShell } from "@/components/ops/module-shell";
import { DataTools } from "@/components/io/data-tools";
import { DocumentsPanel } from "@/components/documents/documents";
import { useShell } from "@/components/shell/shell-context";
import { ItemThumb, PhotoGallery } from "@/components/ui/photos";
import { FileDrop } from "@/components/ui/file-drop";
import { BulkAction, BulkBar, Checkbox, DataTable, toggleKeys, type Column, type SortState } from "@/components/ui/data-table";
import { download } from "@/components/io/data-tools";
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
  /** Items handed to one person together share this (EA-ISS-…). */
  issue_ref: string | null;
  /** Registry, grouped: the identical items this entry stands for. */
  group?: { count: number; members: { id: number; reference: string; serial_number: string | null; acknowledged: boolean }[] };
  purchase_date: string | null;
  purchase_reference: string | null;
  description: string | null;
  purpose: string | null;
  remarks: string | null;
  request_id: number | null;
  updated_at: string;
  version: number;
};
type AssetEvent = { id: number; type: string; message: string | null; actor: Person | null; from_holder: Person | null; to_holder: Person | null; at: string; proofs?: Proof[] };
type AssetEventDetail = AssetEvent & { data: Record<string, unknown>; asset: { id: number; reference: string; name: string; serial_number: string | null }; proofs: Proof[]; can_add_proof: boolean };
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
type Together = { id: number; reference: string; name: string; serial_number: string | null; acknowledged: boolean };
type AssetDetail = Asset & { events: AssetEvent[]; repairs: Repair[]; attachments: Attachment[]; actions: string[]; issued_together: Together[]; identical_in_stock: number };
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

/** `by` names who has to acknowledge, on pages where the holder isn't shown next to the badge ("you" for the holder). */
export function AssetStatusBadge({ a, by }: { a: Pick<Asset, "status" | "awaiting_acknowledgement">; by?: string }) {
  const s = STATUS[a.status];
  if (a.status === "assigned" && a.awaiting_acknowledgement)
    return (
      <span className="inline-flex h-7 min-w-0 max-w-full items-center gap-1.5 rounded-full border border-ink bg-sheet pl-2 pr-2.5 text-[12.5px] font-medium">
        <span className="size-2.5 shrink-0 rounded-full border-2 border-accent" aria-hidden="true" />
        <span className="truncate">{by === "you" ? "Awaiting your acknowledgement" : by ? `Awaiting acknowledgement by ${by}` : "Awaiting acknowledgement"}</span>
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
  { name: "serial_number", label: "Serial number", half: true, hint: "Leave empty to keep the current one" },
  { name: "brand", label: "Brand", half: true },
  { name: "model", label: "Model", half: true },
  { name: "condition", label: "Condition", type: "select", options: CONDITIONS, required: true, half: true },
  { name: "location", label: "Location", half: true, placeholder: "Floor, room or site" },
  { name: "department_id", label: "Department", type: "department", more: true, half: true },
  { name: "purchase_date", label: "Purchase date", type: "date", more: true, half: true },
  { name: "purchase_reference", label: "Purchase reference", more: true, half: true, placeholder: "PO / OR / DR number" },
  { name: "description", label: "Description", type: "textarea", more: true },
  { name: "purpose", label: "Purpose", type: "textarea", more: true },
  { name: "remarks", label: "Remarks", type: "textarea", more: true },
];

/**
 * Registering. Equipment: each piece becomes its own record with its own serial (typed, or numbered
 * automatically). Consumables (clips, pens, paper): one stock line counted in pieces, in Consumables & Stock.
 */
const equipment = (v: Record<string, string>) => v.kind !== "consumable";
const consumable = (v: Record<string, string>) => v.kind === "consumable";
const REGISTER_FIELDS: FieldDef[] = [
  {
    name: "kind", label: "How is it tracked?", type: "choice", required: true,
    options: [{ value: "equipment", label: "Equipment · one record per piece" }, { value: "consumable", label: "Consumable · counted in pieces" }],
  },
  { ...ASSET_FIELDS[0], label: "Name", placeholder: "e.g. Lenovo ThinkPad T14, or Binder clip" },
  { ...ASSET_FIELDS[1], show: equipment },
  { name: "count", label: "How many?", type: "number", required: true, half: true, hint: "Each piece gets its own record and serial", show: equipment },
  { name: "pieces", label: "How many pieces?", type: "number", required: true, half: true, hint: "Recorded as one count, not per piece", show: consumable },
  { name: "unit", label: "Unit", required: true, half: true, placeholder: "pc, box, pack", show: consumable },
  { name: "stock_location", label: "Storage location", required: true, half: true, placeholder: "e.g. Supply cabinet", show: consumable },
  ...ASSET_FIELDS.slice(3, 5),
  ...ASSET_FIELDS.slice(5, 7).map((f) => ({ ...f, show: equipment })),
  { name: "serial_numbers", label: "Serial numbers", type: "textarea", placeholder: "One per line, in order", hint: "Optional. Items without one are numbered automatically, like GPI-IT-00012.", show: equipment },
  ...ASSET_FIELDS.slice(7).map((f) => ({ ...f, show: equipment })),
];

function serialList(v: unknown): string[] {
  return String(v ?? "")
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/* ---------------------------------------------------------------- shared rows */

const rowClass = "group flex items-start gap-3.5 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas sm:items-center sm:gap-4 sm:px-5";

function AssetRow({ a, extra, select }: { a: Asset; extra?: React.ReactNode; select?: { on: boolean; toggle: (on: boolean) => void } }) {
  const [open, setOpen] = useState(false);
  const g = a.group;
  const first = g?.members[0];
  const last = g?.members[g.members.length - 1];
  const inner = (
    <>
          <ItemThumb src={a.photo} icon={Package} className="mt-0.5 sm:mt-0" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate text-[15px] font-bold leading-snug">{a.name}</span>
              {g && <span className="tabular shrink-0 rounded-full bg-ink px-2 py-px text-[12px] font-bold text-white">× {g.count}</span>}
            </span>
            <span className="mt-0.5 flex flex-wrap gap-x-2 text-[12.5px] text-ink-3">
              {g ? (
                <>
                  {a.holder && a.issue_ref && <span className="tabular">{a.issue_ref}</span>}
                  <span className="tabular">
                    SN {first?.serial_number} to {last?.serial_number}
                  </span>
                </>
              ) : (
                <>
                  <span className="tabular">{a.reference}</span>
                  {a.serial_number && <span className="tabular">SN {a.serial_number}</span>}
                </>
              )}
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
    </>
  );
  return (
    <li>
      {select ? (
        <label className={cn(rowClass, "cursor-pointer", select.on && "bg-canvas")}>
          <Checkbox checked={select.on} onChange={select.toggle} label={`Select ${a.name}`} className="mt-3 sm:mt-0" />
          {inner}
        </label>
      ) : (
        <Link href={`/asset/${a.id}`} className={rowClass}>
          {inner}
          <ChevronRight className="mt-3 size-4 shrink-0 text-mute group-hover:text-ink sm:mt-0" strokeWidth={1.75} aria-hidden="true" />
        </Link>
      )}
      {g && (
        <div className="px-4 pb-3 pl-[76px] sm:px-5 sm:pl-[84px]">
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-ctl)] px-1 text-[13px] font-medium text-ink-2 hover:text-ink">
            <ChevronDown className={cn("size-4 transition-transform duration-200", open && "rotate-180")} strokeWidth={1.75} aria-hidden="true" />
            {open ? "Hide" : "Show"} the {g.count} items
          </button>
          {open && (
            <ul className="mt-1 divide-y divide-line rounded-[var(--radius-ctl)] border border-line bg-sheet">
              {g.members.map((m) => (
                <li key={m.id}>
                  <Link href={`/asset/${m.id}`} className="flex items-center justify-between gap-3 px-3 py-2 text-[13px] hover:bg-canvas">
                    <span className="tabular min-w-0 truncate">
                      <span className="font-medium">SN {m.serial_number}</span> <span className="text-ink-3">· {m.reference}</span>
                    </span>
                    {a.holder && <span className="shrink-0 text-[12px] text-ink-3">{m.acknowledged ? "Acknowledged" : "Not yet acknowledged"}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
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

const ids = (a: Asset) => (a.group ? a.group.members.map((m) => m.id) : [a.id]);
const rowKey = (a: Asset) => `${a.id}-${a.group?.count ?? 1}`;
const issuable = (a: Asset) => a.status === "in_stock" && !a.holder;

const COLUMNS: Column<Asset>[] = [
  {
    key: "asset",
    label: "Asset",
    sort: "name",
    render: (a) => (
      <span className="flex items-center gap-3">
        <ItemThumb src={a.photo} icon={Package} />
        <span className="min-w-0">
          <span className="flex items-center gap-2">
            <Link href={`/asset/${a.id}`} className="truncate text-[14px] font-bold hover:underline">
              {a.name}
            </Link>
            {a.group && <span className="tabular shrink-0 rounded-full bg-ink px-2 py-px text-[11.5px] font-bold text-white">× {a.group.count}</span>}
          </span>
          <span className="tabular block truncate text-[12px] text-ink-3">
            {a.group
              ? `${a.holder && a.issue_ref ? `${a.issue_ref} · ` : ""}SN ${a.group.members[0].serial_number} to ${a.group.members[a.group.members.length - 1].serial_number}`
              : `${a.reference}${a.serial_number ? ` · SN ${a.serial_number}` : ""}`}
          </span>
        </span>
      </span>
    ),
  },
  { key: "category", label: "Category", sort: "category", className: "hidden 2xl:table-cell", render: (a) => <span className="text-ink-2">{a.category}</span> },
  {
    key: "holder",
    label: "With / at",
    sort: "holder",
    render: (a) => (a.holder ? <span className="font-medium">{a.holder.name}</span> : <span className="text-ink-3">{a.location ?? "Not issued"}</span>),
  },
  { key: "condition", label: "Condition", sort: "condition", className: "hidden 2xl:table-cell", render: (a) => <span className="text-ink-2">{conditionLabel(a.condition)}</span> },
  { key: "status", label: "Status", sort: "status", render: (a) => <AssetStatusBadge a={a} /> },
  {
    key: "updated",
    label: "Updated",
    sort: "updated",
    align: "right",
    render: (a) => (
      <span className="tabular block whitespace-nowrap text-[12.5px] leading-snug">
        {fmtDate(a.updated_at)}
        <span className="block text-ink-3">{new Date(a.updated_at).toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" })}</span>
      </span>
    ),
  },
];

export function AssetRegistry({ view }: { view?: "assigned" | "under_repair" }) {
  const toast = useToast();
  const router = useRouter();
  const [q, setQ] = useState("");
  const term = useDebounced(q);
  const [status, setStatus] = useState<string | undefined>(view);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState<SortState>({ key: "updated", dir: "desc" });
  const [selected, setSelected] = useState<Map<string, Asset>>(new Map());
  const [selecting, setSelecting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [bulk, setBulk] = useState<"issue" | "stock" | null>(null);
  const data = useApi<AssetPage>(
    `/api/v1/assets${qs({ q: term, status: status && status !== "unacknowledged" ? [status] : undefined, holder: status === "unacknowledged" ? status : undefined, grouped: true, sort: sort.key, dir: sort.dir, page, page_size: pageSize })}`,
  );
  const s = data.data?.summary;
  const rows = data.data?.items ?? [];
  const chosen = [...selected.values()];
  const chosenIds = chosen.flatMap(ids);
  const clear = () => {
    setSelected(new Map());
    setSelecting(false);
  };
  const select = (keys: string[], on: boolean) => setSelected((prev) => toggleKeys(prev, rows, rowKey, keys, on));
  const allIssuable = chosen.length > 0 && chosen.every(issuable);
  // "Move to Consumables & Stock" works per item (every record of the same name and category).
  const items = [...new Map(chosen.map((a) => [`${a.name.trim().toLowerCase()}|${a.category}`, a])).values()];

  async function exportSelected() {
    try {
      const sp = new URLSearchParams({ format: "xlsx" });
      chosenIds.forEach((i) => sp.append("ids", String(i)));
      await download(`/api/v1/exports/assets?${sp}`, "assets-selected.xlsx");
      toast(`Exported ${chosenIds.length} record${chosenIds.length === 1 ? "" : "s"}`);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

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
            <div className="flex gap-2">
              <SearchBox value={q} onChange={(v) => (setQ(v), setPage(1), setSelected(new Map()))} placeholder="Search name, serial, tag or holder" />
              <Button className="lg:hidden" variant={selecting ? "primary" : "secondary"} icon={ListChecks} onClick={() => (selecting ? clear() : setSelecting(true))}>
                {selecting ? "Done" : "Select"}
              </Button>
            </div>
            <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0">
              {VIEWS.map((v) => (
                <Chip key={v.label} on={status === v.value} onClick={() => (setStatus(v.value), setPage(1), setSelected(new Map()))}>
                  {v.label}
                </Chip>
              ))}
            </div>
          </div>
          {data.error ? (
            <ErrorState message={data.error.message} onRetry={data.reload} />
          ) : !data.data ? (
            <SkeletonRows />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={Package}
              title={q || status ? "No matching records" : "No assets yet"}
              body={q || status ? "Try another search or status." : "Register equipment here, or record a delivery in Receiving Proof to register it from a request."}
              compact
            />
          ) : (
            <>
              <DataTable
                rows={rows}
                columns={COLUMNS}
                rowKey={rowKey}
                rowLabel={(a) => a.name}
                href={(a) => `/asset/${a.id}`}
                selected={new Set(selected.keys())}
                onSelect={select}
                sort={sort}
                onSort={(v) => (setSort(v), setPage(1))}
                caption="Assets"
                expand={{
                  label: (a) => (a.group ? `the ${a.group.count} items` : null),
                  render: (a) => (
                    <ul className="divide-y divide-line rounded-[var(--radius-ctl)] border border-line bg-sheet">
                      {a.group!.members.map((m) => (
                        <li key={m.id}>
                          <Link href={`/asset/${m.id}`} className="flex items-center justify-between gap-3 px-3 py-2 text-[13px] hover:bg-canvas">
                            <span className="tabular min-w-0 truncate">
                              <span className="font-medium">SN {m.serial_number}</span> <span className="text-ink-3">· {m.reference}</span>
                            </span>
                            {a.holder && <span className="shrink-0 text-[12px] text-ink-3">{m.acknowledged ? "Acknowledged" : "Not yet acknowledged"}</span>}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ),
                }}
              />
              <ul className="divide-y divide-line lg:hidden">
                {rows.map((a) => (
                  <AssetRow key={rowKey(a)} a={a} select={selecting ? { on: selected.has(rowKey(a)), toggle: (on) => select([rowKey(a)], on) } : undefined} />
                ))}
              </ul>
              <Pager page={page} pageSize={pageSize} total={data.data.total} onPage={setPage} onPageSize={(n) => (setPageSize(n), setPage(1))} />
            </>
          )}
        </Panel>
      </div>
      {/* room so the selection bar never covers the last row */}
      {selected.size > 0 && <div className="h-20" aria-hidden="true" />}
      <BulkBar count={chosenIds.length} onClear={clear}>
        <BulkAction icon={UserPlus} label="Issue" onClick={() => setBulk("issue")} disabled={!allIssuable} title={allIssuable ? undefined : "Only items in stock can be issued"} />
        <BulkAction icon={Download} label="Export" onClick={exportSelected} />
        <BulkAction icon={Boxes} label="Move to Consumables" short="To stock" onClick={() => setBulk("stock")} />
      </BulkBar>
      <RecordDialog
        open={bulk === "issue"}
        onClose={() => setBulk(null)}
        title={`Issue ${chosenIds.length} item${chosenIds.length === 1 ? "" : "s"}`}
        description={`${chosen.map((a) => (a.group ? `${a.name} × ${a.group.count}` : a.name)).join(", ")}. Issued together: one acknowledgement and one issuance form.`}
        fields={[
          { name: "employee_id", label: "Issue to", type: "person", required: true, placeholder: "Choose a person" },
          { name: "date_issued", label: "Date issued", type: "date", half: true, more: true },
          { name: "condition", label: "Condition at issue", type: "select", options: CONDITIONS, half: true, more: true },
          { name: "note", label: "Note", type: "textarea", more: true },
        ]}
        submitLabel={`Issue ${chosenIds.length}`}
        proof={{
          url: (r) => {
            const ev = (r as { event_id?: number } | undefined)?.event_id;
            return ev ? `/api/v1/assets/events/${ev}/proof` : null;
          },
          title: "Proof of handover",
          note: "optional · the items with the person receiving them",
          label: "Issue",
        }}
        onSubmit={async (p) => {
          const r = await post<{ issue_ref: string; count: number; event_id: number; holder: Person }>("/api/v1/assets/issue", { ...p, asset_ids: chosenIds });
          toast(`Issued ${r.count} item${r.count === 1 ? "" : "s"} to ${r.holder.name} · ${r.issue_ref}`);
          clear();
          invalidate();
          return r;
        }}
      />
      <RecordDialog
        open={bulk === "stock"}
        onClose={() => setBulk(null)}
        title="Move to Consumables & Stock"
        description={`Every record of ${items.map((a) => a.name).join(", ")} becomes one stock line each, counted in pieces. Pieces with people are recorded as issued to them. Serial numbers are dropped; photos and files move along.`}
        fields={[
          { name: "location", label: "Storage location", required: true, half: true, placeholder: "e.g. Supply cabinet" },
          { name: "unit", label: "Unit", required: true, half: true },
        ]}
        initial={{ unit: "pc" }}
        submitLabel={`Move ${items.length} item${items.length === 1 ? "" : "s"}`}
        onSubmit={async (p) => {
          const done: string[] = [];
          for (const a of items) {
            try {
              const r = await post<{ item_code: string }>(`/api/v1/assets/${a.id}/to-stock`, p);
              done.push(r.item_code);
            } catch (e) {
              toast(`${a.name}: ${(e as ApiError).message}`, "error");
            }
          }
          if (done.length) toast(`Moved to Consumables & Stock · ${done.join(", ")}`);
          clear();
          invalidate();
          if (done.length === items.length && items.length === 1) router.push("/assets/inventory");
        }}
      />
      <RecordDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Register"
        description="Equipment (laptops, chairs, phones) gets one record and serial per piece. Consumables (clips, pens, paper) are counted in pieces in Consumables & Stock."
        fields={REGISTER_FIELDS}
        initial={{ kind: "equipment", condition: "brand_new", count: "1", unit: "pc" }}
        submitLabel="Register"
        photos="asset"
        onSubmit={async (p) => {
          if (p.kind === "consumable") {
            const i = await post<{ id: number; item_code: string; on_hand: number; unit: string }>("/api/v1/inventory/items", {
              item_code: null, name: p.name, category: "Consumables", unit: p.unit ?? "pc", location: p.stock_location, opening_quantity: p.pieces ?? 0, brand: p.brand, model: p.model,
            });
            toast(`Added to Consumables & Stock · ${i.item_code} · ${i.on_hand} ${i.unit}`);
            invalidate();
            return { ...i, photo_owner: "inventory_item" };
          }
          const { serial_numbers, kind: _kind, ...rest } = p;
          void _kind;
          const a = await post<Asset & { created: { id: number; serial_number: string }[] }>("/api/v1/assets", { ...rest, count: p.count ?? 1, serial_numbers: serialList(serial_numbers) });
          const n = a.created.length;
          toast(n > 1 ? `Registered ${n} items · ${a.created[0].serial_number} to ${a.created[n - 1].serial_number}` : `Registered · SN ${a.serial_number}`);
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
  const [toStock, setToStock] = useState(false);
  const [eventId, setEventId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  if (q.error) return <PageFrame><ErrorState message={q.error.status === 404 ? "This asset doesn't exist or isn't shared with you." : q.error.message} /></PageFrame>;
  const a = q.data;
  if (!a) return <PageFrame><SkeletonRows /></PageFrame>;
  const staff = Boolean(me && me.role !== "employee");
  const has = (k: string) => a.actions.includes(k);
  const n = a.issued_together.length;

  const specs: Record<ActionKey, { title: string; label: string; fields: FieldDef[]; url: string; method?: string; done: string; initial?: Record<string, string> }> = {
    edit: { title: "Edit asset", label: "Save", fields: ASSET_FIELDS, url: `/api/v1/assets/${a.id}`, method: "PATCH", done: "Saved", initial: fromRecord(ASSET_FIELDS, a as unknown as Record<string, unknown>) },
    assign: {
      title: a.identical_in_stock ? `Issue ${a.name}` : "Issue this asset", label: "Issue", url: `/api/v1/assets/${a.id}/assign`, done: "Issued",
      initial: { count: "1" },
      fields: [
        { name: "employee_id", label: "Issue to", type: "person", required: true, placeholder: "Choose a person" },
        ...(a.identical_in_stock
          ? [{ name: "count", label: "How many?", type: "number", required: true, hint: `${a.identical_in_stock + 1} in stock. Issued together: one acknowledgement and one issuance form.` } as FieldDef]
          : []),
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
      const res = await post<AssetDetail>(`/api/v1/assets/${a!.id}/acknowledge`);
      q.setData(res);
      toast(res.issued_together.length > 1 ? `${res.issued_together.length} items acknowledged` : "Receipt acknowledged");
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
            <AssetStatusBadge a={a} by={has("acknowledge") ? "you" : a.holder?.name} />
            <span className="text-[13px] text-ink-2">{conditionLabel(a.condition)}</span>
          </div>
        </div>
      </header>

      {(has("acknowledge") || has("retire") || primary.some(([k]) => has(k))) && (
        <section className="mt-6 rounded-[var(--radius-panel)] border border-ink bg-sheet p-4 sm:p-5">
          <p className="text-[15px] font-bold">{has("acknowledge") ? "Receipt confirmation" : a.holder ? `Issued to ${a.holder.name}` : a.status === "under_repair" ? "Out for repair" : "In stock"}</p>
          <p className="mt-1 text-[14px] text-ink-2">
            {has("acknowledge")
              ? `${a.issued_by?.name ?? "Executive Admin"} issued ${n > 1 ? `${n} of these` : "it"} to you on ${fmtDate(a.date_issued)}.`
              : a.holder
                ? a.acknowledged_at
                  ? `Acknowledged ${fmtDate(a.acknowledged_at)}.`
                  : `Issued ${fmtDate(a.date_issued)} · Waiting for ${a.holder.name} to acknowledge receipt.`
                : a.location
                  ? `At ${a.location}.`
                  : "Not issued to anyone."}
          </p>
          <ActionRow
            className="mt-4"
            danger={
              has("retire") && (
                <Button variant="danger" icon={Archive} onClick={() => setDialog("retire")}>
                  Retire asset
                </Button>
              )
            }
          >
            {has("acknowledge") && (
              <Button variant="primary" icon={CircleCheck} busy={busy} onClick={acknowledge}>
                {n > 1 ? `Acknowledge all ${n}` : "Acknowledge receipt"}
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
              <Link href={`/print/asset/${a.id}`} target="_blank" className={buttonClass("secondary")}>
                <Printer className="size-4" strokeWidth={1.75} aria-hidden="true" />
                Issuance form
              </Link>
            )}
          </ActionRow>
          {staff && has("edit") && (
            <p className="mt-4 border-t border-line pt-3 text-[13px] text-ink-2">
              Counted in pieces, like clips or pens?{" "}
              <button type="button" onClick={() => setToStock(true)} className="font-medium text-ink underline underline-offset-2">
                Move to Consumables &amp; Stock
              </button>
            </p>
          )}
        </section>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-6">
        {/* Photos first on phones; top of the right column on desktop. */}
        <div className="lg:col-start-2 lg:row-start-1">
          <PhotoGallery ownerType="asset" ownerId={a.id} canEdit={staff} />
        </div>
        <div className="flex min-w-0 flex-col gap-5 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          {n > 1 && (
            <Panel title={`Issued together · ${a.issue_ref}`} meta={`${n}`}>
              <ul className="divide-y divide-line">
                {a.issued_together.map((x) => (
                  <li key={x.id}>
                    <Link href={`/asset/${x.id}`} className={cn("flex items-center justify-between gap-3 px-4 py-2.5 text-[13.5px] hover:bg-canvas sm:px-5", x.id === a.id && "bg-canvas")}>
                      <span className="tabular min-w-0 truncate">
                        <span className="font-medium">SN {x.serial_number}</span> <span className="text-ink-3">· {x.reference}</span>
                      </span>
                      <span className="shrink-0 text-[12.5px] text-ink-3">{x.acknowledged ? "Acknowledged" : "Not yet acknowledged"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="History">
            <ol className="px-4 py-4 sm:px-5">
              {a.events.map((e, i) => (
                <li key={e.id} className="relative pb-2 last:pb-0">
                  {i < a.events.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-line" aria-hidden="true" />}
                  <button type="button" onClick={() => setEventId(e.id)} className="-mx-2 flex w-[calc(100%+16px)] gap-3 rounded-[var(--radius-ctl)] px-2 py-1.5 text-left transition-colors duration-150 hover:bg-canvas" aria-label={`${EVENT_LABEL[e.type] ?? e.type}, ${fmtRelative(e.at)}: open details`}>
                    <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full bg-sheet ring-1 ring-edge" aria-hidden="true">
                      <span className="size-1.5 rounded-full bg-ink-3" />
                    </span>
                    <span className="min-w-0 flex-1 pt-0.5">
                      <span className="block text-[13.5px]">
                        <span className="font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>
                        <span className="text-ink-3"> · {e.actor?.name ?? "System"} · {fmtRelative(e.at)}</span>
                      </span>
                      {e.message && <span className="mt-0.5 block text-[13.5px] text-ink-2">{e.message}</span>}
                      {(e.proofs?.length ?? 0) > 0 && (
                        <span className="mt-1.5 flex items-center gap-1.5">
                          {e.proofs!.slice(0, 4).map((p) => (
                            // eslint-disable-next-line @next/next/no-img-element -- private API image
                            <img key={p.id} src={p.thumb} alt="" loading="lazy" className="size-10 rounded-[6px] border border-line object-cover" />
                          ))}
                          <span className="text-[11.5px] text-ink-3">
                            {e.proofs!.length} photo{e.proofs!.length === 1 ? "" : "s"}
                          </span>
                        </span>
                      )}
                    </span>
                    <ChevronRight className="mt-1.5 size-4 shrink-0 text-mute" strokeWidth={1.75} aria-hidden="true" />
                  </button>
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
                ["Quantity", a.quantity > 1 ? `${a.quantity} ${a.unit}` : "—"],
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
        proof={
          dialog && ["assign", "return", "transfer", "retire"].includes(dialog)
            ? {
                url: (s) => {
                  const ev = (s as AssetDetail | undefined)?.events?.[0];
                  return ev ? `/api/v1/assets/events/${ev.id}/proof` : null;
                },
                title: dialog === "assign" ? "Proof of handover" : dialog === "return" ? "Proof of return" : "Photo proof",
                note: dialog === "assign" ? "optional · the item with the person receiving it" : dialog === "return" ? "optional · what came back and its condition" : "optional · date, time and location are stamped on camera photos",
                label: `${spec?.label ?? ""} · ${a.name}`,
              }
            : undefined
        }
        onSubmit={async (p) => {
          const body = dialog === "edit" ? { ...p, version: a.version } : p;
          const res = await api<AssetDetail | Repair>(spec!.url, { method: spec!.method ?? "POST", json: body });
          if ("actions" in res) q.setData(res);
          else q.reload();
          const n = "issued_together" in res ? res.issued_together.length : 0;
          toast(dialog === "assign" && n > 1 && "issue_ref" in res ? `Issued ${n} items · ${res.issue_ref}` : `${spec!.done} · ${a.reference}`);
          invalidate();
          return res;
        }}
      />
      {toStock && <ToStockDialog asset={a} onClose={() => setToStock(false)} />}
      {eventId !== null && <AssetEventDialog id={eventId} onClose={() => setEventId(null)} onChanged={q.reload} />}
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
  async function upload(files: FileList | File[] | null) {
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
          <FileDrop compact busy={busy} onFiles={(f) => upload(f)} hint="PDF, image, Word, Excel or text" />
        </div>
      )}
    </Panel>
  );
}

/* ---------------------------------------------------------------- employee: my assets */

/** One history entry: what happened, who, when, and its photo proof. */
function AssetEventDialog({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const q = useApi<AssetEventDetail>(`/api/v1/assets/events/${id}`);
  const e = q.data;
  const label = e ? EVENT_LABEL[e.type] ?? e.type : "";
  const rows: [string, React.ReactNode][] = e
    ? [
        ["When", fmtDateTime(e.at)],
        ["By", e.actor?.name ?? "System"],
        ...(e.to_holder ? [["To", e.to_holder.name] as [string, React.ReactNode]] : []),
        ...(e.from_holder ? [["From", e.from_holder.name] as [string, React.ReactNode]] : []),
        ...(typeof e.data.condition === "string" ? [["Condition", conditionLabel(e.data.condition)] as [string, React.ReactNode]] : []),
        ...(typeof e.data.issue_ref === "string" ? [["Issuance", e.data.issue_ref] as [string, React.ReactNode]] : []),
        ...(e.message ? [["Note", e.message] as [string, React.ReactNode]] : []),
      ]
    : [];
  return (
    <Dialog open onClose={onClose} wide title={e ? label : "History"} description={e ? `${e.asset.name} · ${e.asset.reference}${e.asset.serial_number ? ` · SN ${e.asset.serial_number}` : ""}` : undefined} footer={<Button onClick={onClose}>Close</Button>}>
      {q.error ? (
        <ErrorState message={q.error.message} />
      ) : !e ? (
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
            <ProofSection
              proofs={e.proofs}
              addUrl={e.can_add_proof ? `/api/v1/assets/events/${e.id}/proof` : undefined}
              label={`${label} · ${e.asset.name}`}
              onAdded={() => {
                q.reload();
                onChanged();
              }}
            />
          </section>
        </div>
      )}
    </Dialog>
  );
}

type ToStockPlan = { name: string; count: number; in_stock: number; issued: { holder: Person; quantity: number }[]; location: string | null; blocked: string | null };

/** Every record of a counted item becomes one stock line: pieces in stock, and pieces issued per person. */
function ToStockDialog({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const toast = useToast();
  const router = useRouter();
  const plan = useApi<ToStockPlan>(`/api/v1/assets/${asset.id}/to-stock`);
  const p = plan.data;
  if (!p) return null;
  const issued = p.issued.map((h) => `${h.quantity} with ${h.holder.name}`).join(", ");
  const summary = `${p.count} ${p.name} record${p.count === 1 ? "" : "s"} become one stock line counted in pieces: ${p.in_stock} in stock${issued ? `, ${issued} (recorded as issued)` : ""}. Serial numbers are dropped; photos and files move with it.`;
  return (
    <RecordDialog
      open
      onClose={onClose}
      title="Move to Consumables & Stock"
      description={p.blocked ?? summary}
      fields={p.blocked ? [] : [
        { name: "location", label: "Storage location", required: true, half: true, placeholder: "e.g. Supply cabinet" },
        { name: "unit", label: "Unit", required: true, half: true },
      ]}
      initial={{ location: p.location ?? "", unit: "pc" }}
      submitLabel={p.blocked ? "Close" : `Move ${p.count} into one stock line`}
      onSubmit={async (v) => {
        if (p.blocked) return;
        const r = await post<{ item_id: number; item_code: string; moved: number }>(`/api/v1/assets/${asset.id}/to-stock`, v);
        toast(`Moved to Consumables & Stock · ${r.item_code}`);
        invalidate();
        router.push(`/stock/${r.item_id}`);
      }}
    />
  );
}

type Supply = { id: number; kind: "issue" | "return"; reference: string; name: string; item_code: string; photo: string | null; quantity: number; unit: string; note: string | null; at: string };

/** Items issued together show (and are acknowledged) as one entry. */
function bundle(list: Asset[]) {
  const out: { a: Asset; count: number }[] = [];
  const seen = new Map<string, { a: Asset; count: number }>();
  for (const a of list) {
    const key = a.issue_ref ? `${a.issue_ref}|${a.awaiting_acknowledgement}` : `one-${a.id}`;
    const hit = seen.get(key);
    if (hit) hit.count++;
    else {
      const e = { a, count: 1 };
      seen.set(key, e);
      out.push(e);
    }
  }
  return out;
}

export function MyAssets() {
  const toast = useToast();
  const q = useApi<Asset[]>("/api/v1/me/assets");
  const supplies = useApi<Supply[]>("/api/v1/me/supplies");
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "Home", href: "/me" }, { label: "My assets" }]} />
      <h1 className="text-[24px] font-bold tracking-[-0.02em] sm:text-[30px]">My assets</h1>
      <p className="mt-2 text-[15.5px] text-ink-2">Equipment and supplies issued to you. Confirm anything you&apos;ve received.</p>
      <div className="mt-8">
        <Panel>
          {!q.data ? (
            <SkeletonRows rows={2} />
          ) : q.data.length === 0 ? (
            supplies.data?.length ? (
              <p className="px-5 py-4 text-[13.5px] text-ink-3">No equipment issued to you.</p>
            ) : (
              <EmptyState icon={Package} title="No assets issued to you" compact />
            )
          ) : (
            <ul className="divide-y divide-line">
              {bundle(q.data).map(({ a, count }) => (
                <li key={a.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                  <Link href={`/asset/${a.id}`} className="flex min-w-0 flex-1 items-start gap-3.5">
                    <ItemThumb src={a.photo} icon={Package} size="lg" />
                    <span className="min-w-0">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-[15px] font-bold">{a.name}</span>
                        {count > 1 && <span className="tabular shrink-0 rounded-full bg-ink px-2 py-px text-[12px] font-bold text-white">× {count}</span>}
                      </span>
                      <span className="block text-[12.5px] text-ink-3">
                        <span className="tabular">{count > 1 ? a.issue_ref : a.reference}</span>
                        {count === 1 && a.serial_number ? ` · SN ${a.serial_number}` : ""} · issued {fmtDate(a.date_issued)}
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
                          toast(count > 1 ? `${count} items acknowledged` : "Receipt acknowledged");
                          invalidate();
                        } catch (e) {
                          toast((e as ApiError).message, "error");
                        }
                      }}
                      className="self-start sm:self-center"
                    >
                      {count > 1 ? `Acknowledge all ${count}` : "Acknowledge receipt"}
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
      {supplies.data && supplies.data.length > 0 && (
        <div className="mt-6">
          <Panel title="Supplies issued to you" meta={`${supplies.data.length}`}>
            <ul className="divide-y divide-line">
              {supplies.data.map((m) => (
                <li key={m.id} className="flex items-center gap-3.5 px-4 py-3 sm:px-5">
                  <ItemThumb src={m.photo} icon={Boxes} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-bold">{m.name}</span>
                    <span className="block text-[12.5px] text-ink-3">
                      {m.kind === "return" ? "Returned" : "Issued"} {fmtDate(m.at)}
                      {m.note ? ` · ${m.note}` : ""}
                    </span>
                  </span>
                  <span className="tabular shrink-0 text-[15px] font-bold">
                    {m.kind === "return" ? "−" : ""}
                    {m.quantity} <span className="text-[12.5px] font-normal text-ink-3">{m.unit}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}
    </PageFrame>
  );
}
