import type { LucideIcon } from "lucide-react";
import {
  ArrowLeftRight,
  BookOpen,
  Building2,
  ClipboardList,
  Crosshair,
  Database,
  DatabaseZap,
  FileText,
  FlaskConical,
  FlaskRound,
  FolderKanban,
  FolderTree,
  FormInput,
  Grid3x3,
  KeyRound,
  LayoutGrid,
  Library,
  Package,
  Pipette,
  ScanLine,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Tag,
  TestTubes,
  Truck,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  children?: NavItem[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navigation: NavGroup[] = [
  {
    label: "Discovery",
    items: [
      { title: "Search", href: "/search", icon: Search },
      { title: "Compounds", href: "/compounds", icon: FlaskConical },
      { title: "Protocols", href: "/assays", icon: TestTubes },
      { title: "Projects", href: "/projects", icon: FolderKanban },
      { title: "Collections", href: "/collections", icon: Library },
      { title: "Saved Searches", href: "/saved-searches", icon: BookOpen },
    ],
  },
  {
    label: "Inventory",
    items: [
      { title: "Batches & Samples", href: "/inventory", icon: Package },
      { title: "Plates", href: "/inventory/plates", icon: LayoutGrid },
      { title: "Plate Groups", href: "/inventory/plate-groups", icon: FolderTree },
      { title: "Loans", href: "/inventory/loans", icon: ArrowLeftRight },
      { title: "Sample Requests", href: "/inventory/sample-requests", icon: ClipboardList },
      { title: "Shipments", href: "/inventory/shipments", icon: Truck },
      { title: "Synthesis Requests", href: "/inventory/synthesis-requests", icon: FlaskRound },
      { title: "Browse by Tag", href: "/tags", icon: Tag },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        title: "Screening Setup",
        href: "/assays/plate-templates",
        icon: Grid3x3,
        children: [
          { title: "Plate Templates", href: "/assays/plate-templates", icon: Grid3x3 },
          { title: "Protocol Forms", href: "/admin/protocol-forms", icon: FileText },
        ],
      },
      {
        title: "Registration Setup",
        href: "/admin/registration-forms",
        icon: FormInput,
        children: [
          { title: "Registration Forms", href: "/admin/registration-forms", icon: FormInput },
          { title: "Custom Fields", href: "/admin/custom-fields", icon: SlidersHorizontal },
          { title: "Salt Catalog", href: "/admin/salt-catalog", icon: Pipette },
        ],
      },
      {
        title: "Vocabularies",
        href: "/admin/vocabularies",
        icon: BookOpen,
        children: [
          { title: "Vocabularies", href: "/admin/vocabularies", icon: BookOpen },
          { title: "Ontology Slots", href: "/admin/ontology-slots", icon: BookOpen },
          { title: "Tags", href: "/admin/tags", icon: Tag },
        ],
      },
      {
        title: "Organization",
        href: "/admin/organizations",
        icon: Building2,
        children: [
          { title: "Organizations", href: "/admin/organizations", icon: Building2 },
          { title: "Data Sources", href: "/admin/data-sources", icon: Database },
          { title: "Targets", href: "/admin/targets", icon: Crosshair },
          { title: "API Keys", href: "/admin/api-keys", icon: KeyRound },
          { title: "Kiosk Devices", href: "/admin/kiosk-devices", icon: ScanLine },
          { title: "Settings", href: "/admin/settings", icon: Settings },
        ],
      },
      { title: "Audit Log", href: "/admin/audit", icon: ShieldCheck },
      {
        title: "Data Import",
        href: "/admin/data-import/cdd",
        icon: DatabaseZap,
        children: [{ title: "CDD Vault", href: "/admin/data-import/cdd", icon: DatabaseZap }],
      },
    ],
  },
];

/** Which nav href is active for a pathname: the LONGEST href (top-level or
 * child) that is the path itself or a whole-segment prefix of it. A section
 * root such as "/inventory" therefore lights up on "/inventory/batches/…" but
 * not on "/inventory/plates", where the sibling's longer href wins. */
export function activeHref(groups: NavGroup[], pathname: string): string | null {
  let best: string | null = null;
  const consider = (href: string) => {
    const matches =
      pathname === href || pathname.startsWith(href.endsWith("/") ? href : `${href}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  };
  for (const group of groups) {
    for (const item of group.items) {
      consider(item.href);
      for (const child of item.children ?? []) consider(child.href);
    }
  }
  return best;
}
