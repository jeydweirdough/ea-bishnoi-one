import { ModulePage } from "@/components/page/module-page";
import { SELF_SERVICE, crumbsFor, selfHref } from "@/lib/nav";

export function SelfServicePage({ slug }: { slug: string }) {
  const item = SELF_SERVICE.find((s) => s.slug === slug)!;
  return (
    <ModulePage
      crumbs={crumbsFor(selfHref(item))}
      href={selfHref(item)}
      item={item}
      siblingsTitle="Self-service"
      siblingsOnMobile={false}
      siblings={SELF_SERVICE.map((s) => ({ href: selfHref(s), label: s.label, code: s.code, current: s.slug === slug }))}
    />
  );
}
