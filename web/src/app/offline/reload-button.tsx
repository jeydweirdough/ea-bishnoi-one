"use client";

export function ReloadButton() {
  return (
    <button
      type="button"
      onClick={() => location.reload()}
      className="mt-6 inline-flex h-11 items-center gap-2.5 rounded-[var(--radius-ctl)] bg-ink pl-3.5 pr-4 text-[15px] font-medium text-white transition-opacity duration-150 hover:opacity-90"
    >
      <span className="size-3 rounded-full border-[2.5px] border-accent" aria-hidden="true" />
      Try again
    </button>
  );
}
