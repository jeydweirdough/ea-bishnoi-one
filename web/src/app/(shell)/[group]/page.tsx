import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { IconTile, iconForHref } from "@/components/icons";
import { Breadcrumbs, PageFrame, PageHeader, StatusLine } from "@/components/page/module-page";
import { isLive } from "@/lib/modules";
import { BUILD_STEPS, GROUPS, crumbsFor, findGroup, groupHref, itemHref, tabItems } from "@/lib/nav";

// Every valid page is prerendered from generateStaticParams; only unknown URLs (404s) render on demand,
// so the title may read params without a Suspense boundary.
export const instant = false;

export function generateStaticParams() {
  return GROUPS.map((g) => ({ group: g.slug }));
}

export async function generateMetadata({ params }: PageProps<"/[group]">): Promise<Metadata> {
  const { group } = await params;
  return { title: findGroup(group)?.label ?? "Not found" };
}

export default async function GroupPage({ params }: PageProps<"/[group]">) {
  const { group: slug } = await params;
  const group = findGroup(slug);
  if (!group) notFound();
  const items = tabItems(group);
  const live = items.filter((i) => isLive(group.slug, i.slug)).length;
  const pending = items.filter((i) => !isLive(group.slug, i.slug));
  const steps = pending.map((i) => i.step).filter((s): s is number => s !== null);
  const first = steps.length ? Math.min(...steps) : null;
  const label = live === items.length ? `All ${live} modules live` : live ? `${live} live · ${pending.length} coming soon` : `${items.length} modules coming soon`;
  return (
    <PageFrame>
      <Breadcrumbs crumbs={crumbsFor(groupHref(group))} />
      <PageHeader display title={group.label} summary={group.summary} icon={iconForHref(groupHref(group))}>
        <StatusLine step={live === items.length ? null : first} code={group.code} label={label} done={live === items.length} />
      </PageHeader>

      <section
        className="mt-8 overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet lg:mt-10"
        aria-labelledby="modules-title"
      >
        <div className="flex items-baseline justify-between border-b border-line px-4 py-3 sm:px-5">
          <h2 id="modules-title" className="text-[15px] font-bold">
            Modules
          </h2>
          <span className="tabular text-[12.5px] text-ink-3">{items.length}</span>
        </div>
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.slug}>
              <Link
                href={itemHref(group, item)}
                className="group flex items-center gap-4 px-4 py-3.5 transition-colors duration-150 hover:bg-canvas sm:px-5"
              >
                <IconTile icon={iconForHref(itemHref(group, item))} size="md" />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-[15px] font-bold leading-snug">{item.label}</span>
                    {item.adminOnly && (
                      <span className="rounded-[5px] px-1.5 py-px text-[11.5px] font-medium text-ink-3 ring-1 ring-line">Admin only</span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[13.5px] leading-snug text-ink-3">{item.summary}</span>
                </span>
                <span className="hidden w-[160px] shrink-0 text-right text-[12.5px] text-ink-3 md:block">
                  {isLive(group.slug, item.slug) ? (
                    <span className="inline-flex items-center gap-1.5 font-medium text-ink">
                      <span className="size-2.5 rounded-full border-2 border-accent" aria-hidden="true" />
                      Live
                    </span>
                  ) : item.step ? (
                    `Phase 2.${item.step} · ${BUILD_STEPS[item.step - 1].split(" & ")[0]}`
                  ) : (
                    "Not yet scheduled"
                  )}
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-mute transition-[color,transform] duration-200 group-hover:translate-x-0.5 group-hover:text-ink"
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </PageFrame>
  );
}
