"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Error from the Executive Admin API, with per-field messages when the server sends them. */
export class ApiError extends Error {
  status: number;
  fields: Record<string, string>;
  /** Extra values the API sent with the error (e.g. `existing_id` on a duplicate). */
  data: Record<string, unknown>;
  constructor(status: number, message: string, fields: Record<string, string> = {}, data: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
    this.data = data;
  }
}

function parseDetail(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    // FastAPI validation errors
    const fields: Record<string, string> = {};
    for (const d of detail as { loc?: (string | number)[]; msg?: string }[]) {
      const key = (d.loc ?? []).filter((p) => p !== "body").join(".");
      if (key) fields[key] = (d.msg ?? "Invalid").replace(/^Value error, /, "");
    }
    return new ApiError(status, "Some fields need attention", fields);
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; fields?: Record<string, string> };
    return new ApiError(status, d.message ?? "Request failed", d.fields ?? {}, detail as Record<string, unknown>);
  }
  if (status === 401) return new ApiError(status, "Sign in to continue");
  return new ApiError(status, status >= 500 ? "The server could not complete this. Try again." : "Request failed");
}

// Tiny global invalidation bus: any mutation can ask every mounted query to refetch.
const listeners = new Set<() => void>();
export function invalidate() {
  listeners.forEach((l) => l());
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      ...rest,
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), Accept: "application/json", ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "You appear to be offline. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw parseDetail(res.status, body);
  return body as T;
}

export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });

export function qs(params: Record<string, string | number | boolean | string[] | null | undefined>) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export type Query<T> = {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
  setData: (d: T) => void;
};

/** Fetch on mount and whenever `path` changes; `null` skips. Keeps the previous data while refetching. */
export function useApi<T>(path: string | null): Query<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    listeners.add(reload);
    return () => {
      listeners.delete(reload);
    };
  }, [reload]);

  useEffect(() => {
    if (!path) return;
    const id = ++seq.current;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag tracks the in-flight request
    setLoading(true);
    api<T>(path)
      .then((d) => {
        if (cancelled || id !== seq.current) return;
        setData(d);
        setError(undefined);
      })
      .catch((e: ApiError) => {
        if (cancelled || id !== seq.current) return;
        setError(e);
      })
      .finally(() => {
        if (!cancelled && id === seq.current) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  return { data, error, loading, reload, setData };
}

/* ------------------------------------------------------------------ types */

export type Person = { id: number; employee_no: string; name: string; designation: string | null; department: string | null };

export type Status =
  | "draft"
  | "submitted"
  | "under_review"
  | "returned"
  | "approved"
  | "rejected"
  | "in_progress"
  | "awaiting_finance"
  | "fulfilled"
  | "closed"
  | "cancelled";

export type Priority = "low" | "normal" | "high" | "critical";
export type Kind = "concern" | "supplies" | "asset" | "local_purchase" | "repair" | "other";

export type Step = {
  id: number;
  position: number;
  name: string;
  status: "waiting" | "pending" | "approved" | "rejected" | "returned" | "skipped";
  approver: Person | null;
  decided_by: Person | null;
  decided_at: string | null;
  activated_at: string | null;
  comment: string | null;
  note: string | null;
};

export type RequestSummary = {
  id: number;
  reference: string;
  kind: Kind;
  kind_label: string;
  category: string | null;
  subject: string;
  status: Status;
  priority: Priority;
  requested_priority: Priority;
  company: { id: number; code: string; name: string };
  department: { id: number; name: string } | null;
  requester: Person;
  assigned_to: Person | null;
  needed_by: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  resolution_due_at: string | null;
  response_due_at: string | null;
  sla: "overdue" | "due_soon" | "on_track" | null;
  escalation_level: number;
  item_count: number;
  current_step: Step | null;
  steps_total: number;
  steps_done: number;
};

export type Item = {
  id?: number;
  item_name: string;
  item_category: string | null;
  description: string | null;
  brand: string | null;
  model: string | null;
  quantity: number;
  unit: string;
  received_quantity?: number;
};

export type Attachment = {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  uploaded_by: Person;
  uploaded_at: string;
  purpose: string | null;
  url: string;
};

export type TimelineEvent = {
  id: number;
  type: string;
  message: string | null;
  from_status: string | null;
  to_status: string | null;
  internal: boolean;
  actor: Person | null;
  at: string;
};

export type RequestDetail = RequestSummary & {
  description: string;
  location: string | null;
  related_asset: string | null;
  purpose: string | null;
  delivery_location: string | null;
  fulfillment_status: string | null;
  department_head: Person | null;
  first_response_at: string | null;
  closed_at: string | null;
  version: number;
  items: Item[];
  steps: Step[];
  timeline: TimelineEvent[];
  attachments: Attachment[];
  actions: string[];
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type Me = {
  employee: Person & { company: { id: number; code: string; name: string } };
  role: "admin" | "assistant" | "employee";
  approver: boolean;
  email: string | null;
  must_change_password: boolean;
  acts_for: number[];
  can: { assign: boolean; set_priority: boolean; configure: boolean };
  unread_notifications: number;
  inbox_count: number;
  navigation: { operations: string[]; self_service: boolean; approval_inbox: boolean };
};

export type Notice = {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
  read: boolean;
};

export type Task = {
  id: number;
  reference: string;
  title: string;
  description: string | null;
  company: { id: number; code: string; name: string };
  assignee: Person | null;
  created_by: Person;
  due_date: string | null;
  overdue: boolean;
  priority: Priority;
  status: "open" | "in_progress" | "done" | "cancelled";
  recurrence: "none" | "daily" | "weekly" | "monthly";
  source_module: string | null;
  source_record_id: number | null;
  completion_note: string | null;
  completed_at: string | null;
  created_at: string;
  attachments?: Attachment[];
};

export type Options = {
  concern_categories: string[];
  supply_categories: string[];
  units: string[];
  priorities: Priority[];
  requester: { employee_no: string; name: string; company: string; department: string | null; department_head: string | null };
};

/* ------------------------------------------------------------------ formatting */

const DATE = new Intl.DateTimeFormat("en-PH", { month: "short", day: "numeric", year: "numeric" });
const DATETIME = new Intl.DateTimeFormat("en-PH", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export function fmtDate(v: string | null | undefined) {
  if (!v) return "—";
  const d = v.length === 10 ? new Date(`${v}T00:00:00`) : new Date(v);
  return DATE.format(d);
}

export function fmtDateTime(v: string | null | undefined) {
  return v ? DATETIME.format(new Date(v)) : "—";
}

export function fmtRelative(v: string | null | undefined) {
  if (!v) return "—";
  const diff = new Date(v).getTime() - Date.now();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60_000) return "just now";
  if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) return rtf.format(Math.round(diff / 3_600_000), "hour");
  if (abs < 7 * 86_400_000) return rtf.format(Math.round(diff / 86_400_000), "day");
  return fmtDate(v);
}

export function fmtSize(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
