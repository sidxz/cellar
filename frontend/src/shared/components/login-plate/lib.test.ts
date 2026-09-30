import { describe, expect, it } from "vitest";
import { mulberry32, noiseWells, tracePoints } from "./lib";

describe("tracePoints", () => {
  it("draws a continuous sigmoid that rises left to right", () => {
    const pts = tracePoints(30, 50, 28, 460, { dx: 0, k: 1 });
    expect(pts.length).toBeGreaterThan(20);
    const byCol = new Map<number, number[]>();
    for (const [r, c] of pts) byCol.set(c, [...(byCol.get(c) ?? []), r]);
    const cols = [...byCol.keys()].sort((a, b) => a - b);
    for (let i = 1; i < cols.length; i++) {
      expect(cols[i]).toBe(cols[i - 1] + 1);
      const prev = byCol.get(cols[i - 1]) as number[];
      const next = byCol.get(cols[i]) as number[];
      // neighbouring columns touch or overlap, and the curve never goes down
      expect(Math.min(...prev)).toBeLessThanOrEqual(Math.max(...next) + 1);
      expect(Math.max(...next)).toBeLessThanOrEqual(Math.max(...prev));
    }
    const first = byCol.get(cols[0]) as number[];
    const last = byCol.get(cols[cols.length - 1]) as number[];
    expect(Math.min(...last)).toBeLessThan(Math.min(...first));
  });

  it("stays inside the plate", () => {
    for (const [r, c] of tracePoints(12, 20, 28, 460, { dx: 0.3, k: 1 })) {
      expect(r >= 0 && r < 12 && c >= 0 && c < 20).toBe(true);
    }
  });
});

describe("tracePoints thickness", () => {
  it("a thicker band lights more wells per column, never fewer", () => {
    const thin = tracePoints(30, 50, 28, 460, { dx: 0, k: 1 }, 1);
    const thick = tracePoints(30, 50, 28, 460, { dx: 0, k: 1 }, 3);
    expect(thick.length).toBeGreaterThan(thin.length);
    const thinCols = new Set(thin.map(([, c]) => c));
    for (const [, c] of thick) expect(thinCols.has(c)).toBe(true);
  });
});

describe("noise", () => {
  it("an imperfect trace drops some wells but keeps the shape", () => {
    const clean = tracePoints(30, 50, 28, 460, { dx: 0, k: 1.5 });
    const rough = tracePoints(30, 50, 28, 460, { dx: 0, k: 1.5 }, 3, mulberry32(5));
    expect(rough.length).toBeLessThan(clean.length);
    expect(rough.length).toBeGreaterThan(clean.length * 0.7);
  });

  it("noise wells land inside the visible plate", () => {
    for (const [r, c, p] of noiseWells(30, 50, 28, 460, 40, mulberry32(9))) {
      expect(r >= 0 && r < 30 && c >= 0 && c < 34).toBe(true);
      expect(p >= 0 && p < 1).toBe(true);
    }
  });
});

describe("no well is emitted twice", () => {
  it("in a jittered trace or in the noise, so React keys stay unique", () => {
    const random = mulberry32(5);
    for (const curve of [
      { dx: -0.14, k: 1.5 },
      { dx: 0.1, k: 2 },
      { dx: -0.02, k: 1.2 },
    ]) {
      const pts = tracePoints(30, 70, 28, 460, curve, 3, random);
      expect(new Set(pts.map(([r, c]) => `${r}:${c}`)).size).toBe(pts.length);
    }
    const noise = noiseWells(30, 70, 28, 460, 30, random);
    expect(new Set(noise.map(([r, c]) => `${r}:${c}`)).size).toBe(noise.length);
    expect(noise.length).toBe(30);
  });
});
