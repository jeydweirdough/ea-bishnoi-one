import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  ApprovalsStatusPage,
  MyRequestsPage,
  NotificationsPage,
  RaiseConcernPage,
  RequestSuppliesPage,
} from "@/components/self/self-pages";
import { SELF_SERVICE } from "@/lib/nav";

const PAGES: Record<string, () => React.ReactNode> = {
  "raise-concern": RaiseConcernPage,
  "request-supplies": RequestSuppliesPage,
  requests: MyRequestsPage,
  "approvals-status": ApprovalsStatusPage,
  notifications: NotificationsPage,
};

// Every valid page is prerendered from generateStaticParams; only unknown URLs (404s) render on demand,
// so the title may read params without a Suspense boundary.
export const instant = false;

export function generateStaticParams() {
  return SELF_SERVICE.filter((s) => s.slug).map((s) => ({ item: s.slug }));
}

export async function generateMetadata({ params }: PageProps<"/me/[item]">): Promise<Metadata> {
  const { item } = await params;
  return { title: SELF_SERVICE.find((s) => s.slug === item)?.label ?? "Not found" };
}

export default async function SelfServiceItem({ params }: PageProps<"/me/[item]">) {
  const { item } = await params;
  const Page = PAGES[item];
  if (!Page) notFound();
  return <Page />;
}
