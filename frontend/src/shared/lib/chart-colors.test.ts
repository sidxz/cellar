import { describe, expect, it } from "vitest";
import {
  WELL_TYPE_COLORS,
  fullEffectControl,
  isActivation,
  protocolWellTypeColors,
  wellTypeColors,
} from "./chart-colors";

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

const isRed = (hex: string) => hue(hex) < 15 || hue(hex) > 345;
const isBlue = (hex: string) => hue(hex) > 200 && hue(hex) < 240;

describe("WELL_TYPE_COLORS", () => {
  // Cellar's default convention (positive control = no effect, % inhibition): the
  // full-effect negative control red, the no-effect positive control blue; never red/green.
  it("draws the default full-effect control red and the no-effect control blue", () => {
    expect(isRed(WELL_TYPE_COLORS.negative_control)).toBe(true);
    expect(isBlue(WELL_TYPE_COLORS.positive_control)).toBe(true);
  });

  it("keeps samples neutral so they don't read as a control", () => {
    expect(saturation(WELL_TYPE_COLORS.sample)).toBeLessThan(0.3);
  });
});

describe("controls coloured by effect", () => {
  // The high anchor (positive under "high", negative under "low") is 0 % for an
  // inhibition and 100 % for an activation.
  it.each([
    ["high", false, "negative_control"],
    ["low", false, "positive_control"],
    ["high", true, "positive_control"],
    ["low", true, "negative_control"],
  ] as const)("%s signal, activation %s: the %s is the full effect", (signal, act, full) => {
    expect(fullEffectControl(signal, act)).toBe(full);
    const none = full === "positive_control" ? "negative_control" : "positive_control";
    const colors = wellTypeColors(signal, act);
    expect(isRed(colors[full])).toBe(true);
    expect(isBlue(colors[none])).toBe(true);
    expect(colors.sample).toBe(WELL_TYPE_COLORS.sample);
  });

  it("an activation is % activation without % inhibition beside it", () => {
    expect(isActivation(["percent_activation"])).toBe(true);
    expect(isActivation(["percent_activation", "z_score"])).toBe(true);
    expect(isActivation(["percent_activation", "percent_inhibition"])).toBe(false);
    expect(isActivation(["percent_control"])).toBe(false);
  });

  it("a protocol's colours follow its signal and readouts", () => {
    const protocol = {
      pos_control_signal: "low",
      readout_definitions: [{ normalizations: ["percent_activation"] }, { normalizations: [] }],
    };
    expect(protocolWellTypeColors(protocol)).toEqual(wellTypeColors("low", true));
    expect(protocolWellTypeColors(undefined)).toEqual(WELL_TYPE_COLORS);
  });
});
