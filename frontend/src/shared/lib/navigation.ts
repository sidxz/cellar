import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Building2,
  ClipboardList,
  FileText,
  FlaskConical,
  FlaskRound,
  FolderKanban,
  Grid3x3,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  Library,
  Package,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  TestTubes,
  Truck,
  Pipette,
  FormInput,
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
      { title: "Plate Templates", href: "/assays/plate-templates", icon: Grid3x3 },
      { title: "Inventory", href: "/inventory", icon: Package },
      { title: "Plates", href: "/inventory/plates", icon: LayoutGrid },
      { title: "Sample Requests", href: "/inventory/sample-requests", icon: ClipboardList },
      { title: "Shipments", href: "/inventory/shipments", icon: Truck },
      { title: "Synthesis Requests", href: "/inventory/synthesis-requests", icon: FlaskRound },
    ],
  },
  {
    label: "Research",
    items: [
      { title: "Projects", href: "/projects", icon: FolderKanban },
      { title: "Collections", href: "/collections", icon: Library },
      { title: "Search", href: "/search", icon: Search },
      { title: "Saved Searches", href: "/saved-searches", icon: Search },
    ],
  },
  {
    label: "Administration",
    items: [
      { title: "Organizations", href: "/admin/organizations", icon: Building2 },
      { title: "Vocabularies", href: "/admin/vocabularies", icon: BookOpen },
      { title: "Custom Fields", href: "/admin/custom-fields", icon: SlidersHorizontal },
      { title: "Salt Catalog", href: "/admin/salt-catalog", icon: Pipette },
      { title: "Registration Forms", href: "/admin/registration-forms", icon: FormInput },
      { title: "API Keys", href: "/admin/api-keys", icon: KeyRound },
      { title: "Ontology Slots", href: "/admin/ontology-slots", icon: BookOpen },
      { title: "Protocol Forms", href: "/admin/protocol-forms", icon: FileText },
      { title: "Audit Log", href: "/admin/audit", icon: ShieldCheck },
      { title: "Settings", href: "/admin/settings", icon: Settings },
    ],
  },
];
