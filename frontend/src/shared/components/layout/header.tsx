"use client";

import { FontToggle } from "@/shared/components/font-toggle";
import { Button } from "@/shared/components/ui/button";
import { Bell, Search } from "lucide-react";
import { Breadcrumbs } from "./breadcrumbs";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  return (
    <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border/60 px-4">
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="sm" className="hidden gap-2 text-muted-foreground md:flex">
          <Search className="size-4" />
          <span className="text-xs">Search</span>
          <kbd className="pointer-events-none ml-1 inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            <span className="text-xs">&#8984;</span>K
          </kbd>
        </Button>
        <FontToggle />
        <ThemeToggle />
        <Button variant="ghost" size="icon" className="relative h-8 w-8">
          <Bell className="size-4" />
          <span className="sr-only">Notifications</span>
        </Button>
      </div>
    </header>
  );
}
