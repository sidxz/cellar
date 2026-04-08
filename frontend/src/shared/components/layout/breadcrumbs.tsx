"use client";

import { navigation } from "@/shared/lib/navigation";
import { ChevronRight, Home } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBreadcrumbOverrides } from "./breadcrumb-context";

const allNavItems = navigation.flatMap((g) =>
  g.items.flatMap((i) => [i, ...(i.children ?? [])]),
);

/** Set of hrefs that have actual pages (from navigation config). */
const linkableHrefs = new Set(allNavItems.map((item) => item.href));

export function Breadcrumbs() {
  const pathname = usePathname();
  const overrides = useBreadcrumbOverrides();
  const segments = pathname.split("/").filter(Boolean);

  function resolveLabel(href: string, segment: string): string {
    const override = overrides.get(segment);
    if (override) return override;
    const match = allNavItems.find((item) => item.href === href);
    if (match) return match.title;
    return segment.charAt(0).toUpperCase() + segment.slice(1);
  }

  if (segments.length === 0) {
    return <span className="text-sm font-medium">Dashboard</span>;
  }

  return (
    <nav className="flex items-center gap-1 text-sm" aria-label="Breadcrumb">
      <Link href="/" className="text-muted-foreground hover:text-foreground transition-colors">
        <Home className="size-3.5" />
      </Link>
      {segments.map((segment, i) => {
        const href = `/${segments.slice(0, i + 1).join("/")}`;
        const isLast = i === segments.length - 1;
        const label = resolveLabel(href, segment);
        const isLinkable = !isLast && linkableHrefs.has(href);
        return (
          <span key={href} className="flex items-center gap-1">
            <ChevronRight className="size-3 text-muted-foreground" />
            {isLinkable ? (
              <Link
                href={href}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                {label}
              </Link>
            ) : (
              <span className={isLast ? "font-medium" : "text-muted-foreground"}>
                {label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
