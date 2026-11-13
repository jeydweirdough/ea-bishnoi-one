import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { IssuanceForm } from "@/components/assets/issuance-form";

export const instant = false;
export const metadata: Metadata = { title: "Asset Issuance Form" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <IssuanceForm id={n} />;
}

export default function Page({ params }: PageProps<"/print/asset/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
