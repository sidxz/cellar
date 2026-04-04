import type { LucideIcon } from "lucide-react";
import {
  Building2,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  Package,
  Settings,
  TestTubes,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navigation: NavGroup[] = [
  {
    label: "Platform",
    items: [{ title: "Dashboard", href: "/", icon: LayoutDashboard }],
  },
  {
    label: "Chemistry",
    items: [
      { title: "Compounds", href: "/compounds", icon: FlaskConical },
      { title: "Assays", href: "/assays", icon: TestTubes },
      { title: "Inventory", href: "/inventory", icon: Package },
    ],
  },
  {
    label: "Research",
    items: [{ title: "Projects", href: "/projects", icon: FolderKanban }],
  },
  {
    label: "Administration",
    items: [
      { title: "Organizations", href: "/admin/organizations", icon: Building2 },
      { title: "Settings", href: "/admin/settings", icon: Settings },
    ],
  },
];
