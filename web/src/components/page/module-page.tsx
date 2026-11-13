import Link from "next/link";
import {
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Info,
  Lock,
  ShieldUser,
  User,
  UserCog,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { IconTile, iconForHref } from "@/components/icons";
import { FieldList } from "@/components/page/field-list";
import { BUILD_STEPS, WORKFLOWS, type Access, type Crumb, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- chrome */

export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  const parent = [...crumbs].reverse().find((c) => c.href);
  return (
    <nav aria-label="Breadcrumb" className="mb-4 lg:mb-6">
      {parent && (
        <Link
          href={parent.href!}
          className="-ml-1 inline-flex min-h-11 items-center gap-1 rounded-[6px] pr-2 text-[14px] font-medium text-ink-2 hover:text-ink sm:hidden"
        >
          <ChevronLeft className="size-4" strokeWidth={1.75} aria-hidden="true" />
          {parent.label}
        </Link>
      )}
      <ol className="hidden flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] text-ink-3 sm:flex">
        <li>
          <span>Executive Admin</span>
        </li>
        {crumbs.map((c, i) => (
          <li key={i} className="flex items-center gap-1.5">
            <ChevronRight className="size-3.5 text-mute" strokeWidth={1.75} aria-hidden="true" />
            {c.href ? (
              <Link href={c.href} className="rounded-[4px] font-medium text-ink-2 hover:text-ink hover:underline">
                {c.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-ink">
                {c.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageFrame({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[1160px] px-4 pb-10 pt-5 sm:px-6 lg:px-10 lg:pt-8">{children}</div>;
}

export function PageHeader({
  title,
  summary,
  icon,
  children,
  actions,
  display = false,
}: {
  title: string;
  summary: string;
  icon: LucideIcon;
  children?: React.ReactNode;
  /** Page-level buttons: under the summary on phones and tablets, top-right of the header on desktop. */
  actions?: React.ReactNode;
  display?: boolean;
}) {
  return (
    <div className="lg:flex lg:items-start lg:justify-between lg:gap-10">
    <header className="flex max-w-[780px] items-start gap-4 sm:gap-5">
      <span className="hidden sm:block">
        <IconTile icon={icon} size="lg" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <span className="sm:hidden">
            <IconTile icon={icon} size="md" />
          </span>
          <h1
            className={cn(
              "font-bold leading-[1.15] text-balance",
              display ? "text-[26px] tracking-[-0.025em] sm:text-[40px]" : "text-[24px] tracking-[-0.02em] sm:text-[30px]",
            )}
          >
            {title}
          </h1>
        </div>
        <p className="mt-2 max-w-[60ch] text-[15.5px] leading-[1.6] text-ink-2 text-pretty sm:text-[16px]">{summary}</p>
        {children}
      </div>
    </header>
    {actions && <div className="mt-5 flex flex-wrap gap-2.5 sm:ml-[68px] lg:ml-0 lg:mt-1 lg:shrink-0 lg:flex-nowrap lg:justify-end">{actions}</div>}
    </div>
  );
}

export function StatusLine({ step, code, label = "Coming soon", done }: { step: number | null; code?: string; label?: string; done?: boolean }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="inline-flex h-8 items-center gap-2 rounded-full border border-edge bg-sheet pl-2.5 pr-3.5 text-[13px] font-bold">
        <span className="size-3 rounded-full border-[2.5px] border-accent" aria-hidden="true" />
        {label}
      </span>
      <span className="text-[13px] text-ink-3">
        {step ? (
          <>
            Planned for <span className="tabular font-medium text-ink-2">Phase 2.{step}</span>
            <span className="hidden sm:inline"> · {BUILD_STEPS[step - 1]}</span>
          </>
        ) : done ? (
          "Working screens"
        ) : (
          "Not yet scheduled"
        )}
        {code && <span className="tabular hidden text-mute sm:inline"> · {code}</span>}
      </span>
    </div>
  );
}

function InlineNote({ text }: { text: string }) {
  return (
    <p className="mt-4 flex max-w-[64ch] gap-2 text-[13.5px] leading-relaxed text-ink-2">
      <Info className="mt-[3px] size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
}

function Sheet({ title, meta, children, className }: { title: string; meta?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet", className)}>
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <h2 className="text-[14.5px] font-bold">{title}</h2>
        {meta && <span className="tabular shrink-0 text-[12.5px] text-ink-3">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------- sections */

function Route({ steps }: { steps: string[] }) {
  return (
    <ol
      className="flex flex-col sm:grid sm:grid-cols-[repeat(var(--n),minmax(0,1fr))] sm:items-start"
      style={{ "--n": steps.length } as React.CSSProperties}
    >
      {steps.map((s, i) => {
        const first = i === 0;
        const last = i === steps.length - 1;
        return (
          <li key={s} className="relative flex min-w-0 items-center gap-3 pb-3 sm:flex-col sm:items-start sm:gap-2 sm:pb-0">
            <span className="relative flex items-center sm:w-full">
              <span
                className={cn(
                  "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full",
                  first ? "bg-ink text-white" : last ? "bg-sheet text-ink ring-1 ring-ink" : "bg-sheet ring-1 ring-edge",
                )}
                aria-hidden="true"
              >
                {first ? (
                  <UserRound className="size-3.5" strokeWidth={2} />
                ) : last ? (
                  <CircleCheck className="size-3.5" strokeWidth={2} />
                ) : (
                  <span className="size-1.5 rounded-full bg-mute" />
                )}
              </span>
              {!last && <span className="ml-1 hidden h-px flex-1 bg-edge sm:block" aria-hidden="true" />}
            </span>
            {!last && <span className="absolute left-3 top-6 h-[calc(100%-12px)] w-px bg-edge sm:hidden" aria-hidden="true" />}
            <span className="pr-2 text-[13px] leading-snug text-ink-2">{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

function WorkflowSheet({ workflows }: { workflows: NonNullable<NavItem["workflows"]> }) {
  return (
    <Sheet title="Approval route" meta="Configurable">
      <div className="divide-y divide-line">
        {workflows.map((w) => (
          <div key={w} className="px-4 py-4 sm:px-5">
            <p className="mb-3 text-[12.5px] font-medium text-ink-3">{WORKFLOWS[w].title}</p>
            <Route steps={WORKFLOWS[w].steps} />
          </div>
        ))}
      </div>
    </Sheet>
  );
}

const ROLE_ICONS: Record<string, LucideIcon> = { Admin: ShieldUser, Assistant: UserCog, Employee: User };

function AccessSheet({ access }: { access: Access }) {
  const rows: [string, string][] = [
    ["Admin", access.admin],
    ["Assistant", access.assistant],
    ["Employee", access.employee],
  ];
  return (
    <Sheet title="Who can use this">
      <ul className="divide-y divide-line">
        {rows.map(([role, value]) => {
          const none = value === "No access";
          const RoleIcon = ROLE_ICONS[role];
          return (
            <li key={role} className="flex items-center gap-3 px-4 py-3 sm:px-5">
              <RoleIcon className={cn("size-[18px] shrink-0", none ? "text-mute" : "text-ink-2")} strokeWidth={1.6} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className={cn("block text-[13.5px] font-medium", none && "text-ink-3")}>{role}</span>
                <span className="block text-[12.5px] leading-snug text-ink-3">{value}</span>
              </span>
              {none ? (
                <Lock className="size-4 shrink-0 text-mute" strokeWidth={1.75} aria-label="No access" />
              ) : (
                <CircleCheck className="size-4 shrink-0 text-ink" strokeWidth={1.75} aria-label="Has access" />
              )}
            </li>
          );
        })}
      </ul>
    </Sheet>
  );
}

export type Sibling = { href: string; label: string; code: string; current?: boolean };

function SiblingSheet({ title, siblings }: { title: string; siblings: Sibling[] }) {
  return (
    <Sheet title={title}>
      <ul className="py-1">
        {siblings.map((s) => {
          const Icon = iconForHref(s.href);
          return (
            <li key={s.href}>
              <Link
                href={s.href}
                aria-current={s.current ? "page" : undefined}
                className={cn(
                  "group flex min-h-11 items-center gap-3 px-4 py-2 transition-colors duration-150 sm:px-5",
                  s.current ? "bg-canvas" : "hover:bg-canvas",
                )}
              >
                <Icon
                  className={cn("size-[18px] shrink-0", s.current ? "text-ink" : "text-ink-3 group-hover:text-ink")}
                  strokeWidth={1.6}
                  aria-hidden="true"
                />
                <span className={cn("flex-1 text-[13.5px]", s.current ? "font-bold" : "text-ink-2 group-hover:text-ink")}>{s.label}</span>
                {s.current ? (
                  <span className="size-1.5 rounded-full bg-accent" aria-label="Current page" />
                ) : (
                  <ChevronRight
                    className="size-4 text-mute transition-[color,transform] duration-200 group-hover:translate-x-0.5 group-hover:text-ink"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </Sheet>
  );
}

/* ---------------------------------------------------------------- page */

export function ModulePage({
  crumbs,
  href,
  item,
  access,
  siblings,
  siblingsTitle,
  siblingsOnMobile = true,
}: {
  siblingsOnMobile?: boolean;
  crumbs: Crumb[];
  href: string;
  item: NavItem;
  access?: Access;
  siblings: Sibling[];
  siblingsTitle: string;
}) {
  const Icon = iconForHref(href);
  const hasMain = Boolean(item.fields?.length || item.workflows?.length);
  return (
    <PageFrame>
      <Breadcrumbs crumbs={crumbs} />
      <PageHeader title={item.label} summary={item.summary} icon={Icon}>
        <StatusLine step={item.step} code={item.code} />
        {item.note && <InlineNote text={item.note} />}
      </PageHeader>

      <div className="mt-8 grid gap-5 lg:mt-10 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          {item.fields && (
            <Sheet title={item.fieldsTitle ?? "Planned record"} meta={`${item.fields.length} fields`}>
              <FieldList fields={item.fields} />
            </Sheet>
          )}
          {item.workflows && <WorkflowSheet workflows={item.workflows} />}
          {!hasMain && (
            <section className="flex flex-col items-center rounded-[var(--radius-panel)] border border-dashed border-edge px-6 py-12 text-center">
              <IconTile icon={Icon} size="lg" />
              <h2 className="mt-4 text-[15px] font-bold">Details arrive with its build step</h2>
              <p className="mt-1.5 max-w-[42ch] text-[13.5px] leading-relaxed text-ink-3">
                The fields and screens for {item.label} get designed when its build step starts.
              </p>
            </section>
          )}
        </div>
        <aside className="flex flex-col gap-5">
          {access && <AccessSheet access={access} />}
          <div className={siblingsOnMobile ? undefined : "hidden lg:block"}>
            <SiblingSheet title={siblingsTitle} siblings={siblings} />
          </div>
        </aside>
      </div>
    </PageFrame>
  );
}
