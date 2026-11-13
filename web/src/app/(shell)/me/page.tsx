import type { Metadata } from "next";
import { MyDashboard } from "@/components/self/self-pages";

export const metadata: Metadata = { title: "My Dashboard" };

export default function MyDashboardPage() {
  return <MyDashboard />;
}
