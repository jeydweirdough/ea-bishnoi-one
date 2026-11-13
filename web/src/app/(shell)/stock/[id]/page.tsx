import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { StockItemView } from "@/components/inventory/inventory";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Stock item" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <StockItemView id={n} />;
}

export default function Page({ params }: PageProps<"/stock/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
