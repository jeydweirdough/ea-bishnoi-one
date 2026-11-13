import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { VehicleDetailView } from "@/components/fleet/fleet";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Vehicle" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <VehicleDetailView id={n} />;
}

export default function Page({ params }: PageProps<"/vehicle/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
