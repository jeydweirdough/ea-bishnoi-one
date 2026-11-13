import type { Metadata } from "next";
import { ApprovalInbox } from "@/components/ops/inbox";
import { INBOX } from "@/lib/nav";

export const metadata: Metadata = { title: INBOX.label };

export default function InboxPage() {
  return <ApprovalInbox />;
}
