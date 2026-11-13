import type { Metadata } from "next";
import { Mark } from "@/components/icons";
import { ReloadButton } from "./reload-button";

export const metadata: Metadata = { title: "Offline" };

export default function Offline() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-6">
      <div className="max-w-[400px]">
        <Mark size={40} />
        <h1 className="mt-6 text-[26px] font-bold leading-tight tracking-[-0.02em]">You’re offline</h1>
        <p className="mt-2 text-[16px] leading-relaxed text-ink-2">
          Executive Admin can’t reach the network. Pages you’ve already opened are still available. Requests can’t be sent until you’re back online.
        </p>
        <ReloadButton />
      </div>
    </main>
  );
}
