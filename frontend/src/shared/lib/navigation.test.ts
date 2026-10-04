import type { WorkspaceRole } from "@duar-auth/nextjs";
import { describe, expect, it } from "vitest";
import { activeHref, activeNavItem, navigation, visibleNavigation } from "./navigation";

const RANK: WorkspaceRole[] = ["viewer", "editor", "admin", "owner"];
/** `allows` predicate for a user holding `role` (same order as the Duar SDK). */
const holding = (role: WorkspaceRole) => (required: WorkspaceRole) =>
  RANK.indexOf(role) >= RANK.indexOf(required);
/** Every title (parents, then their children) the role sees in one group. */
const titlesIn = (role: WorkspaceRole, label: string) =>
  visibleNavigation(navigation, holding(role))
    .find((g) => g.label === label)
    ?.items.flatMap((i) => [i.title, ...(i.children ?? []).map((c) => c.title)]);

describe("activeHref — longest whole-segment prefix wins", () => {
  it("a section root stays active on its own sub-routes only", () => {
    expect(activeHref(navigation, "/inventory")).toBe("/inventory");
    expect(activeHref(navigation, "/inventory/batches/b1")).toBe("/inventory");
    expect(activeHref(navigation, "/inventory/samples/s1")).toBe("/inventory");
  });
  it("a sibling with a longer href wins over the section root", () => {
    expect(activeHref(navigation, "/inventory/plate-groups")).toBe("/inventory/plate-groups");
    expect(activeHref(navigation, "/inventory/plate-groups/g1")).toBe("/inventory/plate-groups");
    expect(activeHref(navigation, "/inventory/loans/l1")).toBe("/inventory/loans");
  });
  it("a collapsible child wins over a top-level item that prefixes it", () => {
    expect(activeHref(navigation, "/assays")).toBe("/assays");
    expect(activeHref(navigation, "/assays/plate-templates")).toBe("/assays/plate-templates");
  });
  it("prefix matching respects segment boundaries and unknown paths match nothing", () => {
    expect(activeHref(navigation, "/inventoryx")).toBeNull();
    expect(activeHref(navigation, "/nowhere")).toBeNull();
  });
});

describe("activeNavItem", () => {
  it("child inherits the parent's iconClass", () => {
    const item = activeNavItem(navigation, "/admin/custom-fields");
    expect(item?.title).toBe("Custom Fields");
    expect(item?.iconClass).toBe("text-emerald-500");
  });
});

describe("activeNavItem — a parent and its first child share an href", () => {
  it("the child wins the tie, so its access rule applies", () => {
    expect(activeNavItem(navigation, "/assays/plate-templates")?.title).toBe("Plate Templates");
    expect(activeNavItem(navigation, "/admin/data-import/cdd")?.title).toBe("CDD Vault");
  });
});

describe("route access — a page needs the role its nav entry requires", () => {
  it.each([
    ["/admin/protocol-forms", "admin"],
    ["/admin/data-sources/ds-1", "admin"],
    ["/admin/settings", "admin"],
    ["/assays/plate-templates", "editor"],
    ["/admin/registration-forms", "editor"],
    ["/admin/data-import/cdd", "editor"],
    ["/admin/audit", undefined],
    ["/compounds", undefined],
  ])("%s needs %s", (path, role) => {
    expect(activeNavItem(navigation, path)?.requires).toBe(role);
  });
});

describe("visibleNavigation — entries the role cannot use are hidden", () => {
  it("a viewer's Administration holds only the Audit Log", () => {
    expect(titlesIn("viewer", "Administration")).toEqual(["Audit Log"]);
  });

  it("an editor gets the setup pages they can change, not the admin-only ones", () => {
    expect(titlesIn("editor", "Administration")).toEqual([
      "Screening Setup",
      "Plate Templates",
      "Registration Setup",
      "Registration Forms",
      "Custom Fields",
      "Salt Catalog",
      "Vocabularies",
      "Vocabularies",
      "Organization",
      "Organizations",
      "Audit Log",
      "Data Import",
      "CDD Vault",
    ]);
  });

  it("an admin sees every entry", () => {
    expect(visibleNavigation(navigation, holding("admin"))).toEqual(navigation);
  });

  it("Discovery and Inventory are the same for every role", () => {
    const rest = (role: WorkspaceRole) =>
      visibleNavigation(navigation, holding(role)).filter((g) => g.label !== "Administration");
    expect(rest("viewer")).toEqual(navigation.filter((g) => g.label !== "Administration"));
  });
});
