import { describe, expect, it } from "vitest";
import { activeHref, navigation } from "./navigation";

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
