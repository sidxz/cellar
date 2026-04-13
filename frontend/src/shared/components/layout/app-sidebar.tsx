"use client";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  SidebarTrigger,
} from "@/shared/components/ui/sidebar";
import { NavMain } from "./nav-main";
import { UserMenu } from "./user-menu";
import { WorkspaceSwitcher } from "./workspace-switcher";

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <NavMain />
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
        <div className="flex items-center justify-between border-t border-sidebar-border px-3 py-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <span className="text-[11px] font-medium tracking-wide text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden">
            openchemvault.com
          </span>
          <SidebarTrigger className="size-7 text-sidebar-foreground/40 hover:text-sidebar-foreground" />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
