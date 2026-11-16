import { describe, expect, it } from "vitest";
import { WELL_TYPE_COLORS } from "./chart-colors";

/** Hue in degrees of a #rrggbb color. */
function hue(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return Number.NaN;
  const d = max - min;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

/** Saturation (HSL) of a #rrggbb color. */
function saturation(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  return max === min ? 0 : (max - min) / (1 - Math.abs(2 * l - 1));
}

describe("WELL_TYPE_COLORS", () => {
  // Positive control (the "hit" end) red, negative control blue — the external platform's
  // convention and its blue → red activity scale; never a red/green pair.
  it("draws positive controls red and negative controls blue", () => {
    const pos = hue(WELL_TYPE_COLORS.positive_control);
    const neg = hue(WELL_TYPE_COLORS.negative_control);
    expect(pos < 15 || pos > 345).toBe(true);
    expect(neg).toBeGreaterThan(200);
    expect(neg).toBeLessThan(240);
  });

  it("keeps samples neutral so they don't read as a control", () => {
    expect(saturation(WELL_TYPE_COLORS.sample)).toBeLessThan(0.3);
  });
});
