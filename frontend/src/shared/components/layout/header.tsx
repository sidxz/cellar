"use client";

import { useAuthz } from "@sentinel-auth/nextjs";
import { LogOut, Search } from "lucide-react";

import { Avatar, AvatarFallback } from "@/shared/components/ui/avatar";
import { Button } from "@/shared/components/ui/button";
import { Separator } from "@/shared/components/ui/separator";
import { useCommandPaletteStore } from "@/shared/lib/stores/command-palette-store";
import { Breadcrumbs } from "./breadcrumbs";
import { FontSizeControl } from "./font-size-control";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  const { user, logout } = useAuthz();
  const openPalette = useCommandPaletteStore((s) => s.setOpen);

  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "?";

  return (
    <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border/60 px-4">
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => openPalette(true)}
          className="hidden gap-2 text-muted-foreground md:flex"
        >
          <Search className="size-4" />
          <span className="text-xs">Search</span>
          <kbd className="pointer-events-none ml-1 inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            <span className="text-xs">&#8984;</span>K
          </kbd>
        </Button>
        <FontSizeControl />
        <ThemeToggle />
        <Separator orientation="vertical" className="mx-1.5 data-[orientation=vertical]:h-5" />
        <div className="flex items-center gap-2">
          <Avatar className="size-7 rounded-lg">
            <AvatarFallback className="rounded-lg text-xs">{initials}</AvatarFallback>
          </Avatar>
          <div className="hidden flex-col text-left leading-tight sm:flex">
            <span className="text-xs font-medium">{user?.name ?? "User"}</span>
            <span className="text-[10px] text-muted-foreground">{user?.email ?? ""}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={logout}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
