"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  type BreadcrumbCrumb,
  useBreadcrumbOverride,
  useBreadcrumbTrail,
} from "@/shared/lib/stores/breadcrumb-store";
import { AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

interface DetailShellProps<T> {
  query: { data: T | undefined; isLoading: boolean };
  backHref?: string;
  backLabel?: string;
  title: (entity: T) => string;
  /** Explicit breadcrumb trail. When provided, overrides URL-based breadcrumbs.
   *  The entity title is automatically appended as the last crumb. */
  breadcrumbTrail?: (entity: T) => BreadcrumbCrumb[];
  badge?: (entity: T) => { status: string; label?: string };
  actions?: (entity: T) => ReactNode;
  notFoundMessage?: string;
  children: (entity: T) => ReactNode;
}

export function DetailShell<T>({
  query,
  backHref,
  backLabel = "Back",
  title,
  breadcrumbTrail,
  badge,
  actions,
  notFoundMessage = "Not found.",
  children,
}: DetailShellProps<T>) {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const lastSegment = segments[segments.length - 1] ?? "";
  const entityTitle = query.data ? title(query.data) : "";

  // Build the full trail if the page provided a trail builder,
  // otherwise fall back to the single-segment override.
  const fullTrail: BreadcrumbCrumb[] =
    query.data && breadcrumbTrail ? [...breadcrumbTrail(query.data), { label: entityTitle }] : [];
  useBreadcrumbTrail(fullTrail);
  useBreadcrumbOverride(!breadcrumbTrail ? lastSegment : "", !breadcrumbTrail ? entityTitle : "");

  if (query.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!query.data) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4 text-muted-foreground">{notFoundMessage}</p>
        {backHref && (
          <Button variant="ghost" size="sm" className="mt-4" asChild>
            <Link href={backHref}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              {backLabel}
            </Link>
          </Button>
        )}
      </div>
    );
  }

  const entity = query.data;
  const badgeProps = badge?.(entity);

  return (
    <div className="space-y-6">
      {backHref && (
        <Button variant="ghost" size="sm" asChild>
          <Link href={backHref}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            {backLabel}
          </Link>
        </Button>
      )}

      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight">{entityTitle}</h1>
          {badgeProps && <StatusBadge status={badgeProps.status} label={badgeProps.label} />}
        </div>
        {actions && <div className="flex items-center gap-2">{actions(entity)}</div>}
      </div>

      {children(entity)}
    </div>
  );
}
