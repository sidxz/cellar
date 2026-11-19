import { describe, expect, it } from "vitest";

import type { ColumnMappingBody } from "@/shared/lib/api/model";
import {
  applySavedMapping,
  isLabelled,
  isMulti,
  mappingProblem,
  oneColumnPerTarget,
  scoreSavedMapping,
} from "./column-targets";

const NEEDS_NAME = "Pick the column with the compound name or the structure.";

describe("mappingProblem", () => {
  it("asks for a Source on a labelled target left without one", () => {
    const mapping: ColumnMappingBody = {
      columns: [
        { header: "Molecule Name", target: "name" },
        { header: "LGCY Batch Name", target: "batch_id", source: "  " },
      ],
    };
    expect(mappingProblem(mapping, false)).toBe('Give "LGCY Batch Name" a Source.');
  });

  it("asks for the name or structure column when neither is mapped", () => {
    const mapping: ColumnMappingBody = {
      columns: [
        { header: "Synonyms", target: "compound_id", source: "Synonyms" },
        { header: "Batch Name", target: "ignore" },
      ],
    };
    expect(mappingProblem(mapping, false)).toBe(NEEDS_NAME);
    // SDF: the structure comes from the record itself.
    expect(mappingProblem(mapping, true)).toBeNull();
  });

  it("passes a mapping with a structure column and every Source given", () => {
    const mapping: ColumnMappingBody = {
      columns: [
        { header: "SMILES", target: "smiles" },
        { header: "Synonyms", target: "compound_id", source: "Synonyms" },
      ],
    };
    expect(mappingProblem(mapping, false)).toBeNull();
  });
});

describe("isLabelled / isMulti", () => {
  it("labels the ID targets and lets only IDs and Don't import repeat", () => {
    expect(isLabelled("batch_id")).toBe(true);
    expect(isLabelled("cas_number")).toBe(true);
    expect(isLabelled("name")).toBe(false);
    expect(isMulti("compound_id")).toBe(true);
    expect(isMulti("batch_id")).toBe(true);
    expect(isMulti("ignore")).toBe(true);
    expect(isMulti("cas_number")).toBe(false);
    expect(isMulti("smiles")).toBe(false);
  });
});

describe("scoreSavedMapping", () => {
  const saved: ColumnMappingBody = {
    columns: [
      { header: "Molecule Name", target: "name" },
      { header: "SMILES", target: "smiles" },
      { header: "Batch Molecule-Batch ID", target: "batch_id", source: "CDD batch ID" },
      { header: "LGCY Batch Name", target: "batch_id", source: "CDD legacy batch ID" },
    ],
  };

  it("scores the share of the saved headers the file has, ignoring case and punctuation", () => {
    expect(
      scoreSavedMapping(saved, ["molecule_name", "smiles", "batch molecule batch id", "Extra"]),
    ).toBe(0.75);
    expect(
      scoreSavedMapping(saved, ["Molecule Name", "SMILES", "Batch Molecule-Batch ID", "LGCY"]),
    ).toBe(0.75);
    expect(scoreSavedMapping(saved, ["Other"])).toBe(0);
  });

  it("scores an empty saved mapping 0", () => {
    expect(scoreSavedMapping({ columns: [] }, ["Molecule Name"])).toBe(0);
  });
});

describe("applySavedMapping", () => {
  it("keeps the file's header spelling and leaves headers it doesn't know as suggested", () => {
    const saved: ColumnMappingBody = {
      columns: [
        { header: "Molecule Name", target: "name" },
        { header: "LGCY Batch Name", target: "batch_id", source: "CDD legacy batch ID" },
        { header: "Batch Name", target: "ignore" },
      ],
    };
    const suggestion: ColumnMappingBody = {
      columns: [
        { header: "molecule_name", target: "ignore" },
        { header: "lgcy-batch-name", target: "ignore" },
        { header: "Batch Name", target: "batch_id", source: "Batch Name" },
        { header: "CAS", target: "cas_number", source: "CAS" },
      ],
    };
    expect(applySavedMapping(saved, suggestion)).toEqual({
      columns: [
        { header: "molecule_name", target: "name", source: null },
        { header: "lgcy-batch-name", target: "batch_id", source: "CDD legacy batch ID" },
        { header: "Batch Name", target: "ignore", source: null },
        { header: "CAS", target: "cas_number", source: "CAS" },
      ],
    });
  });
});

describe("one column per single-valued target", () => {
  it("blocks Preview when two columns go to one single-valued target", () => {
    const mapping: ColumnMappingBody = {
      columns: [
        { header: "Compound", target: "name" },
        { header: "Name", target: "name" },
      ],
    };
    expect(mappingProblem(mapping, false)).toBe(
      '"Compound" and "Name" both go to Compound name; only one column can.',
    );
  });

  it("lets a saved column keep its target and drops a suggestion for it", () => {
    const saved: ColumnMappingBody = { columns: [{ header: "Compound", target: "name" }] };
    const suggestion: ColumnMappingBody = {
      columns: [
        { header: "Compound", target: "ignore" },
        { header: "Name", target: "name" },
        { header: "Synonyms", target: "compound_id", source: "Synonyms" },
      ],
    };
    expect(applySavedMapping(saved, suggestion).columns.map((c) => c.target)).toEqual([
      "name",
      "ignore",
      "compound_id",
    ]);
  });

  it("keeps the first of two suggestions for one target", () => {
    const cols = oneColumnPerTarget(
      [
        { header: "a", target: "salt_code" },
        { header: "b", target: "salt_code" },
      ],
      () => false,
    );
    expect(cols.map((c) => c.target)).toEqual(["salt_code", "ignore"]);
  });
});
