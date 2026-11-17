import { describe, expect, it } from "vitest";
import { clipDiagonal, linearFit, meanSd } from "./math";

describe("meanSd", () => {
  it("gives the mean and the sample SD (n − 1)", () => {
    expect(meanSd([0, 2, 4])).toEqual({ mean: 2, sd: 2, n: 3 });
  });

  it("has no SD for one value and nothing for none", () => {
    expect(meanSd([5])).toEqual({ mean: 5, sd: null, n: 1 });
    expect(meanSd([])).toBeNull();
  });
});

describe("linearFit", () => {
  it("fits the least-squares line", () => {
    expect(linearFit([1, 2, 3], [0, 1, 2])).toEqual({ slope: 1, intercept: -1 });
  });

  it("needs two distinct x values", () => {
    expect(linearFit([2, 2], [1, 3])).toBeNull();
    expect(linearFit([1], [1])).toBeNull();
  });
});

describe("clipDiagonal", () => {
  const box = { x0: 1, x1: 4, y0: 5, y1: 9 };

  it("gives the part of y = x + offset inside the box", () => {
    expect(clipDiagonal(3, box)).toEqual([2, 5, 4, 7]);
    expect(clipDiagonal(5, box)).toEqual([1, 6, 4, 9]);
  });

  it("is null when the line misses the box or only touches a corner", () => {
    expect(clipDiagonal(8, box)).toBeNull();
    expect(clipDiagonal(-4, box)).toBeNull();
    expect(clipDiagonal(1, { x0: 2, x1: 2, y0: 3, y1: 3 })).toBeNull();
  });
});
