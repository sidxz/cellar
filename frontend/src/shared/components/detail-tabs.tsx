"use client";

import { TabsContent, TabsList } from "@/shared/components/ui/tabs";
import { cn } from "@/shared/lib/utils";
import { type ComponentProps, useEffect, useState } from "react";

/** Page sections stay visible while the active workspace scrolls. */
export function DetailTabsList({ className, ...props }: ComponentProps<typeof TabsList>) {
  return (
    <div className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur-sm">
      <div className="overflow-x-auto overflow-y-hidden">
        <TabsList
          variant="line"
          className={cn(
            "w-full justify-start gap-4 p-0 group-data-[orientation=horizontal]/tabs:h-11 [&_[data-slot=tabs-trigger]]:h-11 [&_[data-slot=tabs-trigger]]:flex-none [&_[data-slot=tabs-trigger]]:rounded-none [&_[data-slot=tabs-trigger]]:border-x-0 [&_[data-slot=tabs-trigger]]:border-t-0 [&_[data-slot=tabs-trigger]]:border-b-2 [&_[data-slot=tabs-trigger]]:px-1 [&_[data-slot=tabs-trigger]]:after:hidden [&_[data-slot=tabs-trigger][data-state=active]]:border-b-primary",
            className,
          )}
          {...props}
        />
      </div>
    </div>
  );
}

/** Mount on first visit, then retain filters, selections, and unsaved edits. */
export function DetailTabsContent({
  activeValue,
  value,
  className,
  ...props
}: ComponentProps<typeof TabsContent> & { activeValue: string }) {
  const active = activeValue === value;
  const [visited, setVisited] = useState(active);

  useEffect(() => {
    if (active) setVisited(true);
  }, [active]);

  if (!active && !visited) return null;

  return (
    <TabsContent
      value={value}
      forceMount
      hidden={!active}
      className={cn("data-[state=inactive]:hidden", className)}
      {...props}
    />
  );
}
