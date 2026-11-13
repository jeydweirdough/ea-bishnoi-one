import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { BankCaseView } from "@/components/banking/banking";

// Rendered per request: the id is only known at runtime.
export const instant = false;

export const metadata: Metadata = { title: "Banking case" };

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n < 1) notFound();
  return <BankCaseView id={n} />;
}

export default function Page({ params }: PageProps<"/bank-case/[id]">) {
  return (
    <Suspense fallback={null}>
      <Load params={params} />
    </Suspense>
  );
}
