import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { RequestEditView } from "@/components/requests/request-edit";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Edit request" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <RequestEditView id={n} />;
}

export default function EditRequestPage({ params }: PageProps<"/r/[id]/edit">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
