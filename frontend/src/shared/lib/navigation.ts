import type { WorkspaceRole } from "@duar-auth/nextjs";
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
  /** Tailwind text color for the icon (sidebar only); omit for muted default. */
  iconClass?: string;
  /** Lowest workspace role that can use the page: the role its writes need in
   * the backend. Omit when every member can use it. */
  requires?: WorkspaceRole;
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
      { title: "Search", href: "/search", icon: Search, iconClass: "text-sky-500" },
      { title: "Compounds", href: "/compounds", icon: FlaskConical, iconClass: "text-emerald-500" },
      { title: "Protocols", href: "/assays", icon: TestTubes, iconClass: "text-violet-500" },
      { title: "Projects", href: "/projects", icon: FolderKanban, iconClass: "text-amber-500" },
      { title: "Collections", href: "/collections", icon: Library, iconClass: "text-rose-500" },
      {
        title: "Saved Searches",
        href: "/saved-searches",
        icon: BookOpen,
        iconClass: "text-indigo-500",
      },
    ],
  },
  {
    label: "Inventory",
    items: [
      {
        title: "Batches & Samples",
        href: "/inventory",
        icon: Package,
        iconClass: "text-orange-500",
      },
      { title: "Plates", href: "/inventory/plates", icon: LayoutGrid, iconClass: "text-teal-500" },
      {
        title: "Plate Groups",
        href: "/inventory/plate-groups",
        icon: FolderTree,
        iconClass: "text-cyan-500",
      },
      {
        title: "Loans",
        href: "/inventory/loans",
        icon: ArrowLeftRight,
        iconClass: "text-lime-600",
      },
      {
        title: "Sample Requests",
        href: "/inventory/sample-requests",
        icon: ClipboardList,
        iconClass: "text-fuchsia-500",
      },
      { title: "Shipments", href: "/inventory/shipments", icon: Truck, iconClass: "text-blue-500" },
      {
        title: "Synthesis Requests",
        href: "/inventory/synthesis-requests",
        icon: FlaskRound,
        iconClass: "text-pink-500",
      },
      { title: "Browse by Tag", href: "/tags", icon: Tag, iconClass: "text-yellow-500" },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        title: "Screening Setup",
        href: "/assays/plate-templates",
        icon: Grid3x3,
        iconClass: "text-violet-500",
        children: [
          {
            title: "Plate Templates",
            href: "/assays/plate-templates",
            icon: Grid3x3,
            requires: "editor",
          },
          {
            title: "Protocol Forms",
            href: "/admin/protocol-forms",
            icon: FileText,
            requires: "admin",
          },
        ],
      },
      {
        title: "Registration Setup",
        href: "/admin/registration-forms",
        icon: FormInput,
        iconClass: "text-emerald-500",
        children: [
          {
            title: "Registration Forms",
            href: "/admin/registration-forms",
            icon: FormInput,
            requires: "editor",
          },
          {
            title: "Custom Fields",
            href: "/admin/custom-fields",
            icon: SlidersHorizontal,
            requires: "editor",
          },
          { title: "Salt Catalog", href: "/admin/salt-catalog", icon: Pipette, requires: "editor" },
        ],
      },
      {
        title: "Vocabularies",
        href: "/admin/vocabularies",
        icon: BookOpen,
        iconClass: "text-indigo-500",
        children: [
          {
            title: "Vocabularies",
            href: "/admin/vocabularies",
            icon: BookOpen,
            requires: "editor",
          },
          {
            title: "Ontology Slots",
            href: "/admin/ontology-slots",
            icon: BookOpen,
            requires: "admin",
          },
          {
            title: "Protocol Categories",
            href: "/admin/protocol-categories",
            icon: BookOpen,
            requires: "admin",
          },
          {
            title: "Short Labels",
            href: "/admin/naming-labels",
            icon: BookOpen,
            requires: "admin",
          },
          { title: "Tags", href: "/admin/tags", icon: Tag, requires: "admin" },
        ],
      },
      {
        title: "Organization",
        href: "/admin/organizations",
        icon: Building2,
        iconClass: "text-sky-500",
        children: [
          {
            title: "Organizations",
            href: "/admin/organizations",
            icon: Building2,
            requires: "editor",
          },
          { title: "Data Sources", href: "/admin/data-sources", icon: Database, requires: "admin" },
          { title: "Targets", href: "/admin/targets", icon: Crosshair, requires: "admin" },
          { title: "API Keys", href: "/admin/api-keys", icon: KeyRound, requires: "admin" },
          {
            title: "Kiosk Devices",
            href: "/admin/kiosk-devices",
            icon: ScanLine,
            requires: "admin",
          },
          { title: "Settings", href: "/admin/settings", icon: Settings, requires: "admin" },
        ],
      },
      { title: "Audit Log", href: "/admin/audit", icon: ShieldCheck, iconClass: "text-red-500" },
      {
        title: "Data Import",
        href: "/admin/data-import/cdd",
        icon: DatabaseZap,
        iconClass: "text-amber-500",
        children: [
          {
            title: "CDD Vault",
            href: "/admin/data-import/cdd",
            icon: DatabaseZap,
            requires: "editor",
          },
        ],
      },
    ],
  },
];

/** The nav entry (top-level or child) active for a pathname: the LONGEST href
 * that is the path itself or a whole-segment prefix of it. A section root such
 * as "/inventory" therefore lights up on "/inventory/batches/…" but not on
 * "/inventory/plates", where the sibling's longer href wins. A parent shares
 * its first child's href; on that tie the child (the actual page, with its own
 * `requires`) wins. A child inherits its parent's iconClass so page headers
 * stay colour-consistent with the rail. */
export function activeNavItem(groups: NavGroup[], pathname: string): NavItem | null {
  let best: NavItem | null = null;
  const consider = (item: NavItem, parent?: NavItem) => {
    const href = item.href;
    const matches =
      pathname === href || pathname.startsWith(href.endsWith("/") ? href : `${href}/`);
    if (matches && (best === null || href.length > best.href.length))
      best = { ...item, iconClass: item.iconClass ?? parent?.iconClass };
  };
  for (const group of groups) {
    for (const item of group.items) {
      for (const child of item.children ?? []) consider(child, item);
      consider(item);
    }
  }
  return best;
}

/** Which nav href is active for a pathname — see {@link activeNavItem}. */
export function activeHref(groups: NavGroup[], pathname: string): string | null {
  return activeNavItem(groups, pathname)?.href ?? null;
}

/** The nav a user can use: entries whose `requires` they hold, parents with at
 * least one such child, and groups left with at least one entry. `allows`
 * answers "does the user hold at least this role?". */
export function visibleNavigation(
  groups: NavGroup[],
  allows: (role: WorkspaceRole) => boolean,
): NavGroup[] {
  const usable = (item: NavItem) => !item.requires || allows(item.requires);
  return groups
    .map((group) => ({
      ...group,
      items: group.items.flatMap((item) => {
        if (!usable(item)) return [];
        if (!item.children) return [item];
        const children = item.children.filter(usable);
        return children.length > 0 ? [{ ...item, children }] : [];
      }),
    }))
    .filter((group) => group.items.length > 0);
}
