import { describe, expect, it } from "vitest";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import {
  MAX_NODE_LABEL,
  formatLabel,
  groupTypeColor,
  legendEntries,
  pickRoot,
  stateColor,
  truncateLabel,
} from "./plate-group-tree-utils";

function node(over: Partial<PlateGroupNode> = {}): PlateGroupNode {
  return {
    id: "id-1",
    name: "Group",
    owner_org_id: "org-1",
    plate_count: 0,
    created_by: "user-1",
    created_at: "2026-01-01T00:00:00Z",
    version: 1,
    ...over,
  };
}

describe("groupTypeColor", () => {
  it("uses the legacy palette for the four known types, case-insensitively", () => {
    expect(groupTypeColor("vendor")).toBe("#FFBD50");
    expect(groupTypeColor("VENDOR")).toBe("#FFBD50");
    expect(groupTypeColor("screening")).toBe("#8F7EB5");
    expect(groupTypeColor("master_twin")).toBe("#C3D9E4");
    expect(groupTypeColor("hit_collection")).toBe("#E27D60");
  });
  it("is stable and distinct for unknown types", () => {
    expect(groupTypeColor("custom")).toBe(groupTypeColor("custom"));
    expect(groupTypeColor("custom")).not.toBe(groupTypeColor("other"));
  });
  it("returns the neutral color for an untyped (empty) group", () => {
    expect(groupTypeColor("")).toBe("#707372");
  });
});

describe("stateColor", () => {
  it("maps legacy states and falls back to neutral", () => {
    expect(stateColor("Solubilized")).toBe("#7AB648");
    expect(stateColor("dry")).toBe("#99D2F2");
    expect(stateColor("Retired")).toBe("#94a3b8");
    expect(stateColor(null)).toBe("#707372");
  });
});

describe("formatLabel", () => {
  it("renders well counts and mixed", () => {
    expect(formatLabel("96")).toBe("96-well");
    expect(formatLabel("mixed")).toBe("mixed formats");
    expect(formatLabel(null)).toBeNull();
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
  it("lists distinct states and types present, dedupes, and appends unset/untyped", () => {
    const roots = [
      node({ id: "1", group_type: "vendor", state: "Solubilized" }),
      node({
        id: "2",
        group_type: "vendor",
        state: "Dry",
        children: [node({ id: "2a", group_type: "screening", state: null })],
      }),
    ];
    const { states, types } = legendEntries(roots);
    expect(types.map((t) => t.label)).toEqual(["vendor", "screening"]);
    expect(states.map((s) => s.label)).toEqual(["Solubilized", "Dry", "unset"]);
    expect(types.find((t) => t.label === "vendor")?.color).toBe("#FFBD50");
  });
  it("omits unset when every group has a state and untyped when every group is typed", () => {
    const { states, types } = legendEntries([
      node({ id: "1", group_type: "vendor", state: "Dry" }),
    ]);
    expect(states.some((s) => s.label === "unset")).toBe(false);
    expect(types.some((t) => t.label === "untyped")).toBe(false);
  });
});

describe("pickRoot", () => {
  const roots = [{ id: "r1" }, { id: "r2" }];

  it("keeps the current root when it's still among roots", () => {
    expect(pickRoot(roots, "r1", "r2")).toBe("r2");
  });

  it("falls back to the remembered root when current is gone", () => {
    expect(pickRoot(roots, "r1", "stale")).toBe("r1");
  });

  it("falls back to the first root when neither current nor remembered are valid", () => {
    expect(pickRoot(roots, "stale", "also-stale")).toBe("r1");
    expect(pickRoot(roots, null, null)).toBe("r1");
  });

  it("returns null when there are no roots", () => {
    expect(pickRoot([], "r1", "r1")).toBeNull();
  });
});
