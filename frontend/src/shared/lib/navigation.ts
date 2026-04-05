import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Building2,
  ClipboardList,
  FlaskConical,
  FlaskRound,
  FolderKanban,
  LayoutDashboard,
  Package,
  Settings,
  ShieldCheck,
  TestTubes,
  Truck,
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
      { title: "Sample Requests", href: "/inventory/sample-requests", icon: ClipboardList },
      { title: "Shipments", href: "/inventory/shipments", icon: Truck },
      { title: "Synthesis Requests", href: "/inventory/synthesis-requests", icon: FlaskRound },
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
      { title: "Vocabularies", href: "/admin/vocabularies", icon: BookOpen },
      { title: "Audit Log", href: "/admin/audit", icon: ShieldCheck },
      { title: "Settings", href: "/admin/settings", icon: Settings },
    ],
  },
];
