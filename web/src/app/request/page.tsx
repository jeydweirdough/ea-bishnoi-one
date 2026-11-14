import type { Metadata } from "next";
import { RequestLinkPage } from "@/components/request-link/request-link";

export const metadata: Metadata = {
  title: "Requests & reports",
  description: "Report a problem or request items from Executive Admin, Bishnoi One.",
};

export default function Page() {
  return <RequestLinkPage />;
}
