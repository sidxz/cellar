import { describe, expect, it } from "vitest";
import { linearFit, meanSd } from "./math";

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
