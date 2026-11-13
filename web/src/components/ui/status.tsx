import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleX,
  Clock,
  FilePen,
  Flag,
  Hourglass,
  Landmark,
  LoaderCircle,
  MessageSquareWarning,
  PackageCheck,
  PackagePlus,
  ShoppingCart,
  Store,
  TriangleAlert,
  Undo2,
  Wrench,
  FileQuestionMark,
  type LucideIcon,
} from "lucide-react";
import type { Kind, Priority, Status, Step } from "@/lib/api";
import { cn } from "@/lib/cn";

export const STATUS: Record<Status, { label: string; icon: LucideIcon; tone: "ink" | "mute" | "danger" | "live" }> = {
  draft: { label: "Draft", icon: FilePen, tone: "mute" },
  submitted: { label: "Submitted", icon: CircleDot, tone: "ink" },
  under_review: { label: "Under review", icon: Hourglass, tone: "ink" },
  returned: { label: "Returned for revision", icon: Undo2, tone: "live" },
  approved: { label: "Approved", icon: CircleCheck, tone: "ink" },
  rejected: { label: "Rejected", icon: CircleX, tone: "danger" },
  in_progress: { label: "In progress", icon: LoaderCircle, tone: "ink" },
  awaiting_finance: { label: "Awaiting Finance", icon: Landmark, tone: "ink" },
  fulfilled: { label: "Fulfilled", icon: PackageCheck, tone: "live" },
  closed: { label: "Closed", icon: CircleCheck, tone: "mute" },
  cancelled: { label: "Cancelled", icon: Ban, tone: "mute" },
};

export const KIND_ICON: Record<Kind, LucideIcon> = {
  concern: MessageSquareWarning,
  supplies: PackagePlus,
  asset: ShoppingCart,
  local_purchase: Store,
  repair: Wrench,
  other: FileQuestionMark,
};

export const PRIORITY_LABEL: Record<Priority, string> = { low: "Low", normal: "Normal", high: "High", critical: "Urgent" };

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const s = STATUS[status];
  return (
    <span
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border pl-2 pr-2.5 text-[12.5px] font-medium whitespace-nowrap",
        s.tone === "danger" && "border-danger/30 bg-danger-soft text-danger",
        s.tone === "mute" && "border-line bg-canvas text-ink-3",
        s.tone === "ink" && "border-edge bg-sheet text-ink",
        s.tone === "live" && "border-ink bg-sheet text-ink",
        className,
      )}
    >
      {s.tone === "live" ? (
        <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" />
      ) : (
        <s.icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
      )}
      {s.label}
    </span>
  );
}

/** Priority as a quiet text label; High and Critical earn a flag. */
export function PriorityLabel({ priority, className }: { priority: Priority; className?: string }) {
  const loud = priority === "high" || priority === "critical";
  return (
    <span className={cn("inline-flex items-center gap-1 text-[12.5px] whitespace-nowrap", loud ? "font-medium text-ink" : "text-ink-3", className)}>
      {loud && <Flag className={cn("size-3.5", priority === "critical" && "fill-ink")} strokeWidth={2} aria-hidden="true" />}
      {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function SlaLabel({ sla, className }: { sla: "overdue" | "due_soon" | "on_track" | null; className?: string }) {
  if (sla === "overdue")
    return (
      <span className={cn("inline-flex items-center gap-1 text-[12.5px] font-medium whitespace-nowrap text-danger", className)}>
        <TriangleAlert className="size-3.5" strokeWidth={2} aria-hidden="true" />
        Overdue
      </span>
    );
  if (sla === "due_soon")
    return (
      <span className={cn("inline-flex items-center gap-1 text-[12.5px] font-medium whitespace-nowrap text-ink", className)}>
        <Clock className="size-3.5" strokeWidth={2} aria-hidden="true" />
        Due soon
      </span>
    );
  return null;
}

export const STEP_ICON: Record<Step["status"], LucideIcon> = {
  waiting: CircleDashed,
  pending: Hourglass,
  approved: CircleCheck,
  rejected: CircleX,
  returned: Undo2,
  skipped: Ban,
};
