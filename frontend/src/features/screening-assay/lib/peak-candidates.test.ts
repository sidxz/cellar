import { describe, expect, it } from "vitest";

import { type Candidate, hintsFor, snapTarget } from "./peak-candidates";

const at = (value: number, strength = 20): Candidate => ({ value, direction: "rising", strength });

describe("snapTarget", () => {
  it("is the nearest candidate within reach", () => {
    const found = [at(72.71), at(73.5), at(48.1)];
    expect(snapTarget(found, 72.53, 1.4)).toBe(found[0]);
    expect(snapTarget(found, 73.2, 1.4)).toBe(found[1]);
    // Exactly as far as the click reaches still counts.
    expect(snapTarget([at(50)], 51, 1)?.value).toBe(50);
  });

  it("of two equally near, is the stronger, whatever their order", () => {
    const weak = at(49, 12);
    const strong = at(51, 40);
    expect(snapTarget([weak, strong], 50, 1.4)).toBe(strong);
    expect(snapTarget([strong, weak], 50, 1.4)).toBe(strong);
  });

  it("is null when none is within reach", () => {
    expect(snapTarget([at(72.71), at(48.1)], 60, 1.4)).toBeNull();
    expect(snapTarget([at(72.71)], 72.53, 0.1)).toBeNull();
  });

  it("is null without candidates", () => {
    expect(snapTarget([], 60, 1.4)).toBeNull();
  });
});

describe("hintsFor", () => {
  const main = { low: 50, high: 85 };
  const signals = (entries: Record<string, Candidate[]>) => new Map(Object.entries(entries));

  it("hints at the only candidate inside the range", () => {
    expect(hintsFor(main, signals({ s330: [at(72.71)] }))).toEqual([
      { signal: "s330", value: 72.71 },
    ]);
    // The bounds are inside.
    expect(hintsFor(main, signals({ s330: [at(85)] }))).toEqual([{ signal: "s330", value: 85 }]);
  });

  it("of two inside, hints at the stronger when it is at least twice the other", () => {
    expect(hintsFor(main, signals({ s330: [at(60, 15), at(72.71, 30)] }))).toEqual([
      { signal: "s330", value: 72.71 },
    ]);
    // Twice the next strongest, not the weakest.
    expect(hintsFor(main, signals({ s330: [at(72.71, 30), at(60, 20), at(55, 5)] }))).toEqual([]);
  });

  it("gives none for two of similar strength", () => {
    expect(hintsFor(main, signals({ s330: [at(72.71, 30), at(60, 16)] }))).toEqual([]);
  });

  it("gives none for a clear candidate outside the range, which does not count against one inside", () => {
    expect(hintsFor(main, signals({ s330: [at(45, 90)] }))).toEqual([]);
    expect(hintsFor(main, signals({ s330: [at(45, 90), at(72.71, 12)] }))).toEqual([
      { signal: "s330", value: 72.71 },
    ]);
  });

  it("judges each signal by itself, in the order given", () => {
    expect(
      hintsFor(
        main,
        signals({
          s330: [at(72.71, 30)],
          s350: [at(71, 30), at(60, 28)],
          scattering: [at(74.2, 11)],
          ratio: [],
        }),
      ),
    ).toEqual([
      { signal: "s330", value: 72.71 },
      { signal: "scattering", value: 74.2 },
    ]);
  });
});
