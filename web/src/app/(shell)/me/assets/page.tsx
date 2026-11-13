import type { Metadata } from "next";
import { MyAssets } from "@/components/assets/assets";

export const metadata: Metadata = { title: "My assets" };

export default function MyAssetsPage() {
  return <MyAssets />;
}
