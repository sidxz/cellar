"use client";

import { activeNavItem, navigation } from "@/shared/lib/navigation";
import { cn } from "@/shared/lib/utils";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}

export function PageHeader({ title, subtitle, children }: PageHeaderProps) {
  // Icon + colour come from the sidebar entry for this route, so the page
  // header always matches the rail without every caller re-declaring it.
  const nav = activeNavItem(navigation, usePathname());
  return (
    <div className="mb-2 flex items-center justify-between">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          {nav && <nav.icon className={cn("size-5 shrink-0", nav.iconClass)} />}
          {title}
        </h1>
        {subtitle && <p className="mt-1 text-muted-foreground">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
