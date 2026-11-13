import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { RequestDetailView } from "@/components/requests/request-detail";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Request" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <RequestDetailView id={n} />;
}

export default function RequestPage({ params }: PageProps<"/r/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
