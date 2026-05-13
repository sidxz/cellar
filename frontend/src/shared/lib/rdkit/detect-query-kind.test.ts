import { describe, expect, it } from "vitest";
import { detectQueryKind } from "./detect-query-kind";

describe("detectQueryKind", () => {
  describe("classifies as SMILES (the chemist-typed default)", () => {
    it.each([
      ["c1ccccc1", "aromatic benzene"],
      ["C1=CC=CC=C1", "Kekulé benzene"],
      ["CC(=O)O", "acetic acid"],
      ["Fc1ccc(N)cc1", "para-fluoroaniline"],
      ["[CH3+]", "carbocation — bracket without query primitives"],
      ["[13C]C", "isotope label"],
      ["", "empty string"],
    ])("%s — %s", (input) => {
      expect(detectQueryKind(input)).toBe("smiles");
    });
  });

  describe("classifies as SMARTS when query primitives present", () => {
    it.each([
      ["[!#1]", "negation"],
      ["[$(c1ccccc1)]", "recursive SMARTS"],
      ["[N,O]CC", "atom list"],
      ["[#6;a]1[#6;a][#6;a][#6;a][#6;a][#6;a]1", "property AND inside brackets"],
      ["[c&a]1ccccc1", "ampersand AND inside brackets"],
      ["*c1ccccc1", "any-atom prefix"],
      ["c1ccccc1*", "any-atom suffix"],
      ["C~C", "any-bond"],
    ])("%s — %s", (input) => {
      expect(detectQueryKind(input)).toBe("smarts");
    });
  });

  describe("doesn't false-positive on SMILES atom symbols that contain SMARTS-looking chars", () => {
    it.each([
      ["Cl", "chlorine isn't an any-atom"],
      ["Br", "bromine"],
      ["c1ccc2ccccc2c1", "naphthalene — multiple ring closures"],
    ])("%s — %s", (input) => {
      expect(detectQueryKind(input)).toBe("smiles");
    });
  });
});
