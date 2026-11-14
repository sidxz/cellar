import { describe, expect, it } from "vitest";
import { nameSlots } from "../protocol-name-preview";
import { factSlots, settledSlots } from "./required-facts";

const required = (pattern: string, followsTarget = false) =>
  factSlots(nameSlots(pattern).required, followsTarget);
const optional = (pattern: string, followsTarget = false) =>
  factSlots(nameSlots(pattern).optional, followsTarget);

describe("factSlots", () => {
  it.each([
    ["{target} inhibition", ["target"]],
    ["{organism} growth inhibition", ["organism"]],
    ["{cell_line} cytotoxicity", ["cell_line"]],
    ["{matrix} stability", ["assay_format"]],
    ["{organism} {cell_line} infection [{discriminator}]", ["organism", "cell_line"]],
    ["{discriminator?} solubility", []],
    ["{target?} {organism?} binding", []],
    ["{organism} {strain?} growth inhibition", ["organism"]],
    ["{organism} {strain} growth inhibition", ["organism", "strain"]],
  ])("%s needs %j", (pattern, expected) => {
    expect(required(pattern)).toEqual(expected);
  });

  it("asks a {subject} for the target when the form follows it, else the organism", () => {
    expect(required("{subject} inhibition", true)).toEqual(["target"]);
    expect(required("{subject} inhibition", false)).toEqual(["organism"]);
  });

  it.each([
    ["{organism?} pharmacokinetics", ["organism"]],
    ["{cell_line?} permeability", ["cell_line"]],
    ["{subject?} combination", ["organism"]],
    ["{matrix?} stability", ["assay_format"]],
    ["{discriminator?} solubility", []],
    ["{organism} growth inhibition", []],
    ["{organism} {strain?} growth inhibition", ["strain"]],
  ])("%s may also name %j", (pattern, expected) => {
    expect(optional(pattern)).toEqual(expected);
  });

  it("offers an optional {subject?} as the target when the form follows it", () => {
    expect(optional("{subject?} combination", true)).toEqual(["target"]);
  });
});

describe("settledSlots", () => {
  it("drops the organism once a target is linked: the target implies it", () => {
    expect(settledSlots("whole_cell", true)).toEqual(new Set(["organism"]));
    expect(settledSlots("whole_cell", false)).toEqual(new Set());
  });

  it.each(["biochemical", "physicochemical", "analytical", "in_silico"])(
    "%s has no cells, so no cell line or strain",
    (type) => {
      expect(settledSlots(type, false)).toEqual(new Set(["cell_line", "strain"]));
    },
  );

  it.each(["cell_based", "whole_cell", "admet", "in_vivo"])(
    "%s keeps cell line and strain",
    (type) => {
      expect(settledSlots(type, false)).toEqual(new Set());
    },
  );
});
