import Link from "next/link";
import { PageFrame } from "@/components/page/module-page";

export default function NotFound() {
  return (
    <PageFrame>
      <div className="max-w-[520px] py-10">
        <p className="tabular text-[13px] font-medium text-ink-3">404</p>
        <h1 className="mt-2 text-[28px] font-bold leading-tight tracking-[-0.02em]">This page isn’t in Executive Admin</h1>
        <p className="mt-2 text-[16px] leading-relaxed text-ink-2">
          The address may be mistyped, or the module may have moved. Search finds every module by name or code.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex h-11 items-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink pl-3.5 pr-4 text-[15px] font-medium text-white transition-opacity duration-150 hover:opacity-90"
        >
          <span className="size-3 rounded-full border-[2.5px] border-accent" aria-hidden="true" />
          Go to your home
        </Link>
      </div>
    </PageFrame>
  );
}
