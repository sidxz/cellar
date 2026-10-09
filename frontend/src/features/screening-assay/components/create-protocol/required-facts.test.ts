import { describe, expect, it } from "vitest";
import { requiredNameSlots } from "../protocol-name-preview";
import { requiredFactSlots } from "./required-facts";

const slots = (pattern: string, followsTarget = false) =>
  requiredFactSlots(requiredNameSlots(pattern), followsTarget);

describe("requiredFactSlots", () => {
  it.each([
    ["{target} inhibition", ["target"]],
    ["{organism} growth inhibition", ["organism"]],
    ["{cell_line} cytotoxicity", ["cell_line"]],
    ["{matrix} stability", ["assay_format"]],
    ["{organism} {cell_line} infection [{discriminator}]", ["organism", "cell_line"]],
    ["{discriminator?} solubility", []],
    ["{target?} {organism?} binding", []],
  ])("%s needs %j", (pattern, expected) => {
    expect(slots(pattern)).toEqual(expected);
  });

  it("asks a {subject} for the target when the form follows it, else the organism", () => {
    expect(slots("{subject} inhibition", true)).toEqual(["target"]);
    expect(slots("{subject} inhibition", false)).toEqual(["organism"]);
  });
});
