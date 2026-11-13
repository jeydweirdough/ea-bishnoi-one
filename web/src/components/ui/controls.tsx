"use client";

import { forwardRef, useId } from "react";
import { LoaderCircle, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- button */

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "sm";
  icon?: LucideIcon;
  busy?: boolean;
};

export const buttonClass = (variant: ButtonProps["variant"] = "secondary", size: ButtonProps["size"] = "md") =>
  cn(
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-[var(--radius-ctl)] font-medium whitespace-nowrap transition-[background-color,border-color,color,opacity] duration-150 disabled:cursor-not-allowed disabled:opacity-50",
    size === "md" ? "h-11 px-4 text-[14px] md:h-10" : "h-9 px-3 text-[13.5px]",
    variant === "primary" && "bg-ink text-white hover:bg-ink-2",
    variant === "secondary" && "border border-edge bg-sheet text-ink hover:border-mute hover:bg-canvas",
    variant === "ghost" && "text-ink-2 hover:bg-hover hover:text-ink",
    variant === "danger" && "border border-edge bg-sheet text-danger hover:border-danger/50 hover:bg-danger-soft",
  );

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon: Icon, busy, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} disabled={disabled || busy} aria-busy={busy || undefined} className={cn(buttonClass(variant, size), className)} {...rest}>
      {busy ? (
        <LoaderCircle className="size-4 animate-spin" strokeWidth={2} aria-hidden="true" />
      ) : (
        Icon && <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
      )}
      {children}
    </button>
  );
});

/* ---------------------------------------------------------------- fields */

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
  htmlFor,
  badge,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
  htmlFor?: string;
  /** Small marker beside the label, e.g. "Read from document". */
  badge?: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="flex items-baseline justify-between gap-2">
        <label htmlFor={htmlFor} className="text-[13.5px] font-medium text-ink">
          {label}
          {required && (
            <span className="text-ink-3" aria-hidden="true">
              {" "}
              *
            </span>
          )}
        </label>
        {badge}
      </span>
      {children}
      {error ? (
        <p className="text-[12.5px] leading-snug text-danger" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="text-[12.5px] leading-snug text-ink-3">{hint}</p>
      )}
    </div>
  );
}

const control =
  "w-full rounded-[var(--radius-ctl)] border bg-sheet px-3 text-[15px] text-ink placeholder:text-mute transition-[border-color,box-shadow] duration-150 hover:border-mute focus:border-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:bg-canvas disabled:text-ink-3 md:text-[14px]";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return <input ref={ref} aria-invalid={invalid || undefined} className={cn(control, "h-11 md:h-10", invalid ? "border-danger" : "border-edge", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(
  function Textarea({ className, invalid, rows = 4, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        rows={rows}
        aria-invalid={invalid || undefined}
        className={cn(control, "resize-y py-2.5 leading-relaxed", invalid ? "border-danger" : "border-edge", className)}
        {...rest}
      />
    );
  },
);

export function Select({
  className,
  invalid,
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cn(
        control,
        "h-11 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22 fill=%22none%22 stroke=%22%236b6b6b%22 stroke-width=%221.75%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><path d=%22m4 6 4 4 4-4%22/></svg>')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat pr-9 md:h-10",
        invalid ? "border-danger" : "border-edge",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}

/** Pill segmented choice; use for short enumerations such as priority. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; icon?: LucideIcon }[];
  label: string;
  className?: string;
}) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className={cn("flex flex-wrap gap-1.5", className)}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <label
            key={o.value}
            className={cn(
              "inline-flex h-10 cursor-pointer items-center gap-2 rounded-full border px-3.5 text-[13.5px] font-medium transition-colors duration-150 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/60 md:h-9",
              on ? "border-ink bg-ink text-white" : "border-edge bg-sheet text-ink-2 hover:border-mute hover:text-ink",
            )}
          >
            <input type="radio" name={name} className="sr-only" checked={on} onChange={() => onChange(o.value)} />
            {o.icon && <o.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />}
            {o.label}
          </label>
        );
      })}
    </div>
  );
}

export function Switch({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center gap-3 rounded-[var(--radius-ctl)] py-1.5 text-left disabled:opacity-50"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-medium">{label}</span>
        {hint && <span className="block text-[12.5px] leading-snug text-ink-3">{hint}</span>}
      </span>
      <span className={cn("relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200", checked ? "bg-ink" : "bg-edge")}>
        <span
          className={cn(
            "absolute top-0.5 size-4 rounded-full bg-white transition-[left] duration-200 ease-[var(--ease-out-expo)]",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </span>
    </button>
  );
}

/** Filter chip (toggle). */
export function Chip({ on, onClick, children, count }: { on: boolean; onClick: () => void; children: React.ReactNode; count?: number }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors duration-150",
        on ? "border-ink bg-ink text-white" : "border-line bg-sheet text-ink-2 hover:border-edge hover:text-ink",
      )}
    >
      {children}
      {count !== undefined && <span className={cn("tabular text-[12px]", on ? "text-white/70" : "text-ink-3")}>{count}</span>}
    </button>
  );
}
