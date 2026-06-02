import { describe, expect, it } from "vitest";
import { CATEGORY_COLORS, resolveCategoryColor } from "./category-colors";

describe("resolveCategoryColor", () => {
  it("is stable for the same label", () => {
    expect(resolveCategoryColor("project").hex).toBe(resolveCategoryColor("project").hex);
  });
  it("returns a palette member", () => {
    const c = resolveCategoryColor("assay");
    expect(CATEGORY_COLORS.some((p) => p.hex === c.hex)).toBe(true);
  });
  it("different keys can map to different colors", () => {
    const keys = ["project", "assay", "series", "target", "favorite", "status"];
    const hexes = new Set(keys.map((k) => resolveCategoryColor(k).hex));
    expect(hexes.size).toBeGreaterThan(1);
  });
  it("honors an explicit hex when valid", () => {
    expect(resolveCategoryColor("x", "#3b82f6").hex).toBe("#3b82f6");
  });
});
