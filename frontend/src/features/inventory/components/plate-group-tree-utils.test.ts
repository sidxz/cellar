import { describe, expect, it } from "vitest";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import {
  MAX_NODE_LABEL,
  groupTypeColor,
  legendEntries,
  truncateLabel,
} from "./plate-group-tree-utils";

function node(over: Partial<PlateGroupNode> = {}): PlateGroupNode {
  return {
    id: "id-1",
    name: "Group",
    owner_org_id: "org-1",
    plate_count: 0,
    created_by: "user-1",
    version: 1,
    ...over,
  };
}

describe("groupTypeColor", () => {
  it("is stable across calls for the same input", () => {
    expect(groupTypeColor("vendor")).toBe(groupTypeColor("vendor"));
  });

  it("differs for different group types", () => {
    expect(groupTypeColor("vendor")).not.toBe(groupTypeColor("screening"));
  });

  it("returns the neutral color for an untyped (empty) group", () => {
    expect(groupTypeColor("")).toBe("#707372");
  });
});

describe("truncateLabel", () => {
  it("passes short names through unchanged", () => {
    expect(truncateLabel("Vendor batch A")).toBe("Vendor batch A");
  });

  it("passes a name of exactly MAX_NODE_LABEL chars through unchanged", () => {
    const name = "A".repeat(MAX_NODE_LABEL);
    expect(truncateLabel(name)).toBe(name);
  });

  it("truncates a 40-char name to 28 chars with a trailing ellipsis", () => {
    const name = "A".repeat(40);
    const result = truncateLabel(name);
    expect(result.length).toBe(28);
    expect(result.endsWith("…")).toBe(true);
    expect(result).toBe(`${"A".repeat(27)}…`);
  });
});

describe("legendEntries", () => {
  it("dedupes repeated group types across roots and children", () => {
    const roots = [
      node({ id: "1", group_type: "vendor" }),
      node({
        id: "2",
        group_type: "vendor",
        children: [node({ id: "2a", group_type: "screening" })],
      }),
    ];
    const entries = legendEntries(roots);
    const vendorEntries = entries.filter((e) => e.label === "vendor");
    expect(vendorEntries).toHaveLength(1);
    expect(entries.some((e) => e.label === "screening")).toBe(true);
    expect(entries).toHaveLength(2);
  });

  it("omits the untyped entry when every group is typed", () => {
    const roots = [node({ id: "1", group_type: "vendor" })];
    const entries = legendEntries(roots);
    expect(entries.some((e) => e.label === "untyped")).toBe(false);
  });

  it("appends a single untyped entry when an untyped group exists, regardless of how many", () => {
    const roots = [
      node({ id: "1", group_type: "vendor" }),
      node({ id: "2", group_type: "" }),
      node({ id: "3", group_type: undefined }),
    ];
    const entries = legendEntries(roots);
    const untyped = entries.filter((e) => e.label === "untyped");
    expect(untyped).toHaveLength(1);
    expect(entries.at(-1)).toEqual({ label: "untyped", color: "#707372" });
  });

  it("returns a single entry (no untyped) when the whole tree is one type", () => {
    const roots = [
      node({ id: "1", group_type: "vendor" }),
      node({ id: "2", group_type: "vendor", children: [node({ id: "2a", group_type: "vendor" })] }),
    ];
    expect(legendEntries(roots)).toHaveLength(1);
  });

  it("returns a single untyped entry when nothing is typed", () => {
    const roots = [node({ id: "1", group_type: "" }), node({ id: "2", group_type: null })];
    expect(legendEntries(roots)).toEqual([{ label: "untyped", color: "#707372" }]);
  });
});
