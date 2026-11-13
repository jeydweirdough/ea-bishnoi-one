import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ModulePage } from "@/components/page/module-page";
import { LiveModule } from "@/components/ops/live-module";
import { isLive } from "@/lib/modules";
import { GROUPS, crumbsFor, findItem, itemHref } from "@/lib/nav";

// Every valid page is prerendered from generateStaticParams; only unknown URLs (404s) render on demand,
// so the title may read params without a Suspense boundary.
export const instant = false;

export function generateStaticParams() {
  return GROUPS.flatMap((g) => g.items.map((i) => ({ group: g.slug, item: i.slug })));
}

export async function generateMetadata({ params }: PageProps<"/[group]/[item]">): Promise<Metadata> {
  const { group, item } = await params;
  const found = findItem(group, item);
  return { title: found ? found.item.label : "Not found" };
}

export default async function ItemPage({ params }: PageProps<"/[group]/[item]">) {
  const { group: g, item: i } = await params;
  const found = findItem(g, i);
  if (!found) notFound();
  const { group, item } = found;
  const href = itemHref(group, item);
  if (isLive(group.slug, item.slug)) {
    return <LiveModule moduleKey={`${group.slug}/${item.slug}`} meta={{ href, label: item.label, summary: item.summary }} />;
  }
  return (
    <ModulePage
      crumbs={crumbsFor(href)}
      href={href}
      item={item}
      access={item.access ?? group.access}
      siblingsTitle={`Also in ${group.label}`}
      siblings={group.items
        .filter((s) => !s.adminOnly || s.slug === item.slug)
        .map((s) => ({ href: itemHref(group, s), label: s.label, code: s.code, current: s.slug === item.slug }))}
    />
  );
}
