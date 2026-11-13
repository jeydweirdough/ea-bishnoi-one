import type { Metadata } from "next";
import { NewRequestChooser } from "@/components/self/new-request";

export const metadata: Metadata = { title: "New request" };

export default function NewRequestPage() {
  return <NewRequestChooser />;
}
