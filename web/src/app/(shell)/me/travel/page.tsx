import type { Metadata } from "next";
import { MyTravel } from "@/components/travel/travel";

export const metadata: Metadata = { title: "My travel" };

export default function MyTravelPage() {
  return <MyTravel />;
}
