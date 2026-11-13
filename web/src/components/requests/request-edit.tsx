"use client";

import { Pencil } from "lucide-react";
import { useApi, type RequestDetail } from "@/lib/api";
import { Breadcrumbs, PageFrame, PageHeader } from "@/components/page/module-page";
import { ErrorState } from "@/components/ui/feedback";
import { RequestForm } from "./request-form";

export function RequestEditView({ id }: { id: number }) {
  const q = useApi<RequestDetail>(`/api/v1/requests/${id}`);
  if (q.error) return <PageFrame><ErrorState message={q.error.message} onRetry={q.reload} /></PageFrame>;
  const d = q.data;
  if (!d) return <PageFrame><span className="sr-only">Loading</span></PageFrame>;
  if (!d.actions.includes("edit"))
    return (
      <PageFrame>
        <ErrorState message="This request can no longer be edited. Only drafts and requests returned for changes are editable." />
      </PageFrame>
    );
  const items = ["supplies", "asset", "local_purchase"].includes(d.kind);
  return (
    <PageFrame>
      <Breadcrumbs crumbs={[{ label: "My Requests", href: "/me/requests" }, { label: d.reference, href: `/r/${d.id}` }, { label: "Edit" }]} />
      <PageHeader title={d.status === "returned" ? "Revise and resubmit" : "Edit draft"} summary={`${d.reference} · ${d.kind_label}`} icon={Pencil} />
      <RequestForm mode={items ? "supplies" : "concern"} initial={d} />
    </PageFrame>
  );
}
