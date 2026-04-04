"use client";

import { navigation } from "@/shared/lib/navigation";
import { ChevronRight, Home } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const allNavItems = navigation.flatMap((g) => g.items);

function resolveLabel(href: string, segment: string): string {
  const match = allNavItems.find((item) => item.href === href);
  if (match) return match.title;
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}

export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

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
        return (
          <span key={href} className="flex items-center gap-1">
            <ChevronRight className="size-3 text-muted-foreground" />
            {isLast ? (
              <span className="font-medium">{label}</span>
            ) : (
              <Link
                href={href}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
