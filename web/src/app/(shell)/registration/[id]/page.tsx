import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { RegistrationDetailView } from "@/components/compliance/compliance";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Registration" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <RegistrationDetailView id={n} />;
}

export default function Page({ params }: PageProps<"/registration/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
