import { CircleCheck, UserRound } from "lucide-react";
import { fmtDateTime, type RequestSummary, type Step } from "@/lib/api";
import { STEP_ICON } from "@/components/ui/status";
import { cn } from "@/lib/cn";

const STEP_LABEL: Record<Step["status"], string> = {
  waiting: "Waiting",
  pending: "Deciding now",
  approved: "Approved",
  rejected: "Rejected",
  returned: "Returned for changes",
  skipped: "Skipped",
};

/** Vertical approval route: requester → stages → processing. Reads like a receipt, not a stepper. */
export function ApprovalRoute({ steps, requester, submittedAt, done }: { steps: Step[]; requester: string; submittedAt: string | null; done: boolean }) {
  return (
    <ol className="relative">
      <Node icon={UserRound} filled title={requester} sub={submittedAt ? `Submitted ${fmtDateTime(submittedAt)}` : "Not submitted yet"} />
      {steps.map((s) => {
        const Icon = STEP_ICON[s.status];
        return (
          <Node
            key={s.id}
            icon={Icon}
            live={s.status === "pending" || s.status === "returned"}
            filled={s.status === "approved"}
            danger={s.status === "rejected"}
            muted={s.status === "waiting" || s.status === "skipped"}
            title={s.name}
            sub={
              <>
                <span className={cn(s.status === "pending" && "font-medium text-ink")}>{STEP_LABEL[s.status]}</span>
                {" · "}
                {s.decided_by ? (
                  <>
                    {s.decided_by.name}
                    {s.approver && s.decided_by.id !== s.approver.id ? ` for ${s.approver.name}` : ""}, {fmtDateTime(s.decided_at)}
                  </>
                ) : (
                  (s.approver?.name ?? <span className="text-danger">No approver assigned</span>)
                )}
              </>
            }
            note={s.comment ?? s.note}
          />
        );
      })}
      <Node icon={CircleCheck} last filled={done} muted={!done} title="Executive Admin processing" sub={done ? "Approvals complete" : "After all approvals"} />
    </ol>
  );
}

function Node({
  icon: Icon,
  title,
  sub,
  note,
  filled,
  live,
  danger,
  muted,
  last,
}: {
  icon: typeof UserRound;
  title: string;
  sub: React.ReactNode;
  note?: string | null;
  filled?: boolean;
  live?: boolean;
  danger?: boolean;
  muted?: boolean;
  last?: boolean;
}) {
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!last && <span className="absolute left-[13px] top-7 h-[calc(100%-24px)] w-px bg-line" aria-hidden="true" />}
      <span
        className={cn(
          "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full",
          filled && "bg-ink text-white",
          live && "bg-sheet text-ink ring-2 ring-accent",
          danger && "bg-danger-soft text-danger ring-1 ring-danger/40",
          muted && !filled && "bg-sheet text-mute ring-1 ring-line",
          !filled && !live && !danger && !muted && "bg-sheet text-ink ring-1 ring-edge",
        )}
        aria-hidden="true"
      >
        <Icon className="size-3.5" strokeWidth={2} />
      </span>
      <div className="min-w-0 pt-0.5">
        <p className={cn("text-[14px] font-medium leading-snug", muted && "text-ink-3")}>{title}</p>
        <p className="mt-0.5 text-[12.5px] leading-snug text-ink-3">{sub}</p>
        {note && <p className="mt-1.5 rounded-[6px] bg-canvas px-2.5 py-1.5 text-[13px] leading-relaxed text-ink-2">“{note}”</p>}
      </div>
    </li>
  );
}

/** Compact progress used in lists: N of M approvals and who has it now. */
export function RouteProgress({ r }: { r: RequestSummary }) {
  if (!r.steps_total) return null;
  return (
    <span className="mt-2 flex items-center gap-2" aria-label={`${r.steps_done} of ${r.steps_total} approvals`}>
      {/* One joined line, not loose pills: the stages read as one route. */}
      <span className="flex h-1.5 overflow-hidden rounded-full bg-line" style={{ width: r.steps_total * 22 }} aria-hidden="true">
        {Array.from({ length: r.steps_total }, (_, i) => (
          <span key={i} className={cn("h-full flex-1 border-r-2 border-sheet last:border-r-0", i < r.steps_done ? "bg-ink" : i === r.steps_done && r.current_step ? "bg-accent" : "bg-line")} />
        ))}
      </span>
      <span className="tabular text-[12px] text-ink-3">
        {r.steps_done}/{r.steps_total}
      </span>
    </span>
  );
}
