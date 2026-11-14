"use client";

import { useState } from "react";
import { CalendarClock, Check, ChevronDown, CircleCheck, ListTodo, Play, Plus, Repeat, Ban } from "lucide-react";
import { fmtDate, invalidate, post, api, qs, useApi, type ApiError, type Page, type Priority, type Task } from "@/lib/api";
import { iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { Button, Chip, Field, Input, Segmented, Select, Textarea } from "@/components/ui/controls";
import { ACCEPT_DOCS, ChosenFile, FileDrop } from "@/components/ui/file-drop";
import { Dialog, EmptyState, ErrorState, Pager, Panel, SkeletonRows, useToast } from "@/components/ui/feedback";
import { PRIORITY_LABEL, PriorityLabel } from "@/components/ui/status";
import { PeoplePicker } from "@/components/requests/people-picker";
import { useShell } from "@/components/shell/shell-context";
import { DataTools } from "@/components/io/data-tools";
import { crumbsFor } from "@/lib/nav";
import { cn } from "@/lib/cn";

type TaskPage = Page<Task> & { mine: { open: number; in_progress: number; done: number; overdue: number } };
type View = "mine" | "all" | "created";

const STATUS_LABEL: Record<Task["status"], string> = { open: "Open", in_progress: "In progress", done: "Done", cancelled: "Cancelled" };
const RECUR_LABEL: Record<Task["recurrence"], string> = { none: "Once", daily: "Daily", weekly: "Weekly", monthly: "Monthly" };

export function TasksPage({ summary }: { summary: string }) {
  const { me } = useShell();
  const toast = useToast();
  const admin = me?.role === "admin";
  const [view, setView] = useState<View>("mine");
  const [state, setState] = useState<"active" | "overdue" | "done">("active");
  const [page, setPage] = useState(1);
  const status = state === "done" ? ["done", "cancelled"] : ["open", "in_progress"];
  const q = useApi<TaskPage>(`/api/v1/tasks${qs({ view, status, overdue: state === "overdue", page, page_size: 25 })}`);
  const [creating, setCreating] = useState(false);
  const [completing, setCompleting] = useState<Task | null>(null);

  async function setStatus(t: Task, s: "in_progress" | "cancelled") {
    try {
      await api(`/api/v1/tasks/${t.id}`, { method: "PATCH", json: { status: s } });
      toast(s === "in_progress" ? "Started" : "Cancelled");
      invalidate();
    } catch (e) {
      toast((e as ApiError).message, "error");
    }
  }

  return (
    <PageFrame>
      <Breadcrumbs crumbs={crumbsFor("/administration/tasks")} />
      <PageHeader
        title="Tasks"
        summary={summary}
        icon={iconForHref("/administration/tasks")}
        actions={
          <>
            <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
              New task
            </Button>
            <DataTools dataset="tasks" />
          </>
        }
      />



      <div className="mt-8 lg:mt-10">
        <Panel>
          <div className="flex flex-col gap-2 border-b border-line p-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="no-scrollbar -mx-3 flex gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:px-0">
              {(["active", "overdue", "done"] as const).map((s) => (
                <Chip key={s} on={state === s} onClick={() => (setState(s), setPage(1))} count={view === "mine" && q.data ? (s === "active" ? q.data.mine.open + q.data.mine.in_progress : s === "overdue" ? q.data.mine.overdue : undefined) : undefined}>
                  {s === "active" ? "Active" : s === "overdue" ? "Overdue" : "Done"}
                </Chip>
              ))}
            </div>
            <Select aria-label="Whose tasks" value={view} onChange={(e) => (setView(e.target.value as View), setPage(1))} className="sm:w-[200px]">
              <option value="mine">Assigned to me</option>
              <option value="created">Created by me</option>
              <option value="all">{admin ? "All tasks" : "All I can see"}</option>
            </Select>
          </div>
          {q.error ? (
            <ErrorState message={q.error.message} onRetry={q.reload} />
          ) : !q.data ? (
            <SkeletonRows />
          ) : q.data.items.length === 0 ? (
            <EmptyState icon={CircleCheck} title={state === "done" ? "No completed tasks" : "No tasks here"} body="Create a task to assign follow-ups, renewals or recurring checks." compact />
          ) : (
            <>
              <ul className="divide-y divide-line">
                {q.data.items.map((t) => {
                  const active = t.status === "open" || t.status === "in_progress";
                  const mineToDo = admin || t.assignee?.id === me?.employee.id;
                  return (
                    <li key={t.id} className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:px-5">
                      <span className="flex min-w-0 flex-1 items-start gap-3.5">
                        <span className={cn("mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[10px] border", t.status === "done" ? "border-ink bg-ink text-white" : "border-line bg-sheet")} aria-hidden="true">
                          {t.status === "done" ? <Check className="size-5" strokeWidth={2} /> : <ListTodo className="size-5" strokeWidth={1.6} />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={cn("block text-[15px] font-bold leading-snug", t.status === "cancelled" && "text-ink-3 line-through")}>{t.title}</span>
                          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-ink-3">
                            <span className="tabular">{t.reference}</span>
                            <span aria-hidden="true">·</span>
                            <span>{t.assignee?.name ?? "Unassigned"}</span>
                            <span aria-hidden="true">·</span>
                            <span className={cn("inline-flex items-center gap-1", t.overdue && "font-medium text-danger")}>
                              <CalendarClock className="size-3.5" strokeWidth={2} aria-hidden="true" />
                              {t.due_date ? `${t.overdue ? "Overdue · " : ""}${fmtDate(t.due_date)}` : "No due date"}
                            </span>
                            {t.recurrence !== "none" && (
                              <span className="inline-flex items-center gap-1">
                                <Repeat className="size-3.5" strokeWidth={2} aria-hidden="true" />
                                {RECUR_LABEL[t.recurrence]}
                              </span>
                            )}
                            <span aria-hidden="true">·</span>
                            <span>{STATUS_LABEL[t.status]}</span>
                          </span>
                          {t.completion_note && <span className="mt-1.5 block text-[13px] text-ink-2">Done: {t.completion_note}</span>}
                        </span>
                        <PriorityLabel priority={t.priority} className="mt-1 hidden sm:inline-flex" />
                      </span>
                      {active && mineToDo && (
                        <span className="flex gap-2 sm:pl-0 pl-[54px]">
                          {t.status === "open" && (
                            <Button size="sm" icon={Play} onClick={() => setStatus(t, "in_progress")}>
                              Start
                            </Button>
                          )}
                          <Button size="sm" variant="primary" icon={Check} onClick={() => setCompleting(t)}>
                            Complete
                          </Button>
                          {(admin || t.created_by.id === me?.employee.id) && (
                            <Button size="sm" variant="ghost" icon={Ban} aria-label="Cancel task" onClick={() => setStatus(t, "cancelled")}>
                              <span className="sr-only sm:not-sr-only">Cancel</span>
                            </Button>
                          )}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
              <Pager page={page} pageSize={25} total={q.data.total} onPage={setPage} />
            </>
          )}
        </Panel>
      </div>

      <NewTaskDialog open={creating} onClose={() => setCreating(false)} />
      <CompleteDialog task={completing} onClose={() => setCompleting(null)} />
    </PageFrame>
  );
}

function NewTaskDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { me } = useShell();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState<number | null>(null);
  const [due, setDue] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [recurrence, setRecurrence] = useState<Task["recurrence"]>("none");
  const [more, setMore] = useState(false);
  const [err, setErr] = useState<ApiError>();
  const [busy, setBusy] = useState(false);
  const canAssignOthers = me?.role === "admin" || me?.can.assign;

  async function save() {
    setBusy(true);
    setErr(undefined);
    try {
      const t = await post<Task>("/api/v1/tasks", { title, description: description || null, assignee_id: assignee ?? (canAssignOthers ? null : me?.employee.id), due_date: due || null, priority, recurrence });
      toast(`Task created · ${t.reference}`);
      setTitle("");
      setDescription("");
      setDue("");
      setRecurrence("none");
      onClose();
      invalidate();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title="New task"
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" busy={busy} disabled={!title.trim()} onClick={save}>
            Create task
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Title" required htmlFor="t-title" error={err?.fields.title}>
          <Input id="t-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Assign to" htmlFor="t-assignee" hint={canAssignOthers ? undefined : "Assistants assign tasks to themselves unless delegated"} error={err?.fields.assignee_id}>
            {canAssignOthers ? <PeoplePicker id="t-assignee" value={assignee} onChange={setAssignee} role={["admin", "assistant"]} placeholder="Unassigned" /> : <Input id="t-assignee" value={me?.employee.name ?? ""} disabled />}
          </Field>
          <Field label="Due date" htmlFor="t-due" error={err?.fields.due_date}>
            <Input id="t-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
        </div>
        <button type="button" onClick={() => setMore((m) => !m)} aria-expanded={more} className="-ml-1 inline-flex h-10 items-center gap-2 self-start px-1 text-[14px] font-bold">
          <ChevronDown className={cn("size-4 transition-transform duration-200", more && "rotate-180")} strokeWidth={2} aria-hidden="true" />
          More options
          {!more && <span className="text-[13px] font-normal text-ink-3">details, priority, repeat</span>}
        </button>
        {more && (
          <>
            <Field label="Details" htmlFor="t-desc">
              <Textarea id="t-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            <Field label="Priority">
          <Segmented<Priority> label="Priority" value={priority} onChange={setPriority} options={(["low", "normal", "high", "critical"] as Priority[]).map((p) => ({ value: p, label: PRIORITY_LABEL[p] }))} />
            </Field>
            <Field label="Repeats" hint="When completed, the next one is created automatically.">
          <Segmented<Task["recurrence"]> label="Repeats" value={recurrence} onChange={setRecurrence} options={(["none", "daily", "weekly", "monthly"] as const).map((r) => ({ value: r, label: RECUR_LABEL[r] }))} />
            </Field>
          </>
        )}
        {err && !Object.keys(err.fields).length && (
          <p role="alert" className="text-[13.5px] text-danger">
            {err.message}
          </p>
        )}
      </div>
    </Dialog>
  );
}

function CompleteDialog({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();

  async function done() {
    if (!task) return;
    setBusy(true);
    setErr(undefined);
    try {
      if (file) {
        const fd = new FormData();
        fd.set("owner_type", "task");
        fd.set("owner_id", String(task.id));
        fd.set("purpose", "completion");
        fd.set("file", file);
        await api("/api/v1/attachments", { method: "POST", body: fd });
      }
      await post(`/api/v1/tasks/${task.id}/complete`, { note });
      toast(task.recurrence !== "none" ? "Completed · next one scheduled" : "Task completed");
      setNote("");
      setFile(null);
      onClose();
      invalidate();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={Boolean(task)}
      onClose={onClose}
      title="Complete task"
      description={task?.title}
      footer={
        <>
          <Button onClick={onClose}>Back</Button>
          <Button variant="primary" icon={Check} busy={busy} disabled={!note.trim()} onClick={done}>
            Mark complete
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="What was done?" required htmlFor="c-note" error={err}>
          <Textarea id="c-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <FileDrop accept={ACCEPT_DOCS} multiple={false} title="Evidence (optional)" hint="PDF, image, Word, Excel or text, up to 10 MB" inputLabel="Evidence (optional)" onFiles={(f) => setFile(f[0])}>
          {file && <ChosenFile file={file} onRemove={() => setFile(null)} />}
        </FileDrop>
      </div>
    </Dialog>
  );
}
