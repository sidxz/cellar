import Papa from "papaparse";
import { describe, expect, it } from "vitest";

import type { LayoutFile, LayoutFileRow } from "../types";
import type { LabellingRow } from "./labelling-rows";
import { applyLabelMatches, applyLayout, labelsToMatch, layoutTemplateCsv } from "./layout-file";

const rows: LabellingRow[] = [
  {
    key: "a",
    positionLabel: "Position 1",
    used: true,
    label: "Protein alone, buffer",
    note: "bubble",
    wellType: "reference",
    moleculeId: null,
    moleculeName: null,
    moleculeRef: null,
    batchId: null,
    batchNumber: null,
    dose: "",
  },
  {
    key: "b",
    positionLabel: "Position 2",
    used: true,
    label: "x",
    note: "",
    wellType: "sample",
    moleculeId: "m1",
    moleculeName: "Compound one",
    moleculeRef: "REG-0001",
    batchId: "b1",
    batchNumber: "B-1",
    dose: "10",
  },
  {
    key: "c",
    positionLabel: "Position 3",
    used: false,
    label: "",
    note: "",
    wellType: "positive_control",
    moleculeId: "m2",
    moleculeName: "Compound two",
    moleculeRef: "REG-0002",
    batchId: null,
    batchNumber: null,
    dose: "",
  },
];

const OPEN = { allowUse: true, calculatedLocked: false };

function fileRow(position: string, values: Partial<LayoutFileRow> = {}): LayoutFileRow {
  return {
    position,
    label: null,
    note: null,
    well_type: null,
    dose: null,
    use: null,
    compound: null,
    problems: [],
    ...values,
  };
}

const file = (...fileRows: LayoutFileRow[]): LayoutFile => ({
  rows: fileRows,
  unrecognised_columns: [],
  calculated_columns_ignored: false,
});

/** What the API answers for the template written from these rows. */
function fileFromRows(rs: readonly LabellingRow[]): LayoutFile {
  return file(
    ...rs.map((r) =>
      fileRow(r.positionLabel, {
        label: r.label || null,
        note: r.note || null,
        well_type: r.wellType,
        dose: r.dose === "" ? null : Number(r.dose),
        use: r.used,
        compound: r.moleculeId
          ? {
              molecule_id: r.moleculeId,
              molecule_name: r.moleculeName ?? "",
              registration_number: r.moleculeRef ?? "",
              batch_id: r.batchId,
              batch_number: r.batchNumber,
              needs_batch_choice: !r.batchId,
            }
          : null,
      }),
    ),
  );
}

const compound = {
  molecule_id: "m9",
  molecule_name: "Compound nine",
  registration_number: "REG-0009",
  batch_id: "b9",
  batch_number: "B-9",
  needs_batch_choice: false,
};

describe("layout template", () => {
  it("writes a template that starts with a byte-order mark and names the dose unit in the header", () => {
    const csv = layoutTemplateCsv(rows, { doseUnit: "µM", withUse: true });
    expect(csv.startsWith("﻿Position,Label,Role,Compound,Batch,Concentration (µM),Note,Use")).toBe(
      true,
    );
  });

  it("writes one line per row in order with the table's current values, quoting a label with a comma", () => {
    const csv = layoutTemplateCsv(rows, { doseUnit: "µM", withUse: true });
    const lines = csv.split("\r\n");
    expect(lines).toHaveLength(4);
    expect(lines[1]).toBe('Position 1,"Protein alone, buffer",Reference,,,,bubble,Yes');
    expect(lines[2]).toBe("Position 2,x,Sample,REG-0001,B-1,10,,Yes");
    expect(lines[3]).toBe("Position 3,,Positive Control,REG-0002,,,,No");
    expect(Papa.parse(csv.slice(1)).data[1]).toEqual([
      "Position 1",
      "Protein alone, buffer",
      "Reference",
      "",
      "",
      "",
      "bubble",
      "Yes",
    ]);
  });

  it("leaves out the Use column when withUse is false", () => {
    const csv = layoutTemplateCsv(rows, { doseUnit: "nM", withUse: false });
    const lines = csv.split("\r\n");
    expect(lines[0]).toBe("﻿Position,Label,Role,Compound,Batch,Concentration (nM),Note");
    expect(lines[2]).toBe("Position 2,x,Sample,REG-0001,B-1,10,");
  });
});

describe("apply layout", () => {
  it("round-trips: applying the template's own values changes nothing", () => {
    expect(applyLayout(rows, fileFromRows(rows), OPEN)).toMatchObject({
      rows,
      filled: 0,
      problems: [],
      notices: [],
    });
  });

  it("empty cells leave the current value", () => {
    const out = applyLayout(rows, file(fileRow("Position 2", { dose: 12.5 })), OPEN);
    expect(out.rows[1]).toEqual({ ...rows[1], dose: "12.5" });
    expect(out.rows[0]).toBe(rows[0]);
    expect(out.filled).toBe(1);
  });

  it("matches the position after trimming both sides", () => {
    const out = applyLayout(rows, file(fileRow("  Position 1 ", { label: "y" })), OPEN);
    expect(out.rows[0].label).toBe("y");
    expect(out.problems).toEqual([]);
  });

  it("an edited Position matches nothing and is listed and skipped", () => {
    const out = applyLayout(rows, file(fileRow("Position 2 (edited)", { label: "y" })), OPEN);
    expect(out.rows).toEqual(rows);
    expect(out.problems).toEqual(["Position 2 (edited): not a position in this table; skipped"]);
    expect(out.filled).toBe(0);
  });

  it("skips a row with no Position", () => {
    const out = applyLayout(rows, file(fileRow("", { label: "y" })), OPEN);
    expect(out.rows).toEqual(rows);
    expect(out.problems).toEqual(["A row with no Position was skipped"]);
  });

  it("a position that appears twice is listed and skipped", () => {
    const out = applyLayout(
      rows,
      file(
        fileRow("Position 2", { label: "first" }),
        fileRow("Position 2", { label: "second" }),
        fileRow("Position 3", { label: "z" }),
      ),
      OPEN,
    );
    expect(out.rows[1]).toBe(rows[1]);
    expect(out.rows[2].label).toBe("z");
    expect(out.problems).toEqual(["Position 2: appears more than once in the file; skipped"]);
    expect(out.filled).toBe(1);
  });

  it("lists a row problem by position and still fills the row's other columns", () => {
    const out = applyLayout(
      rows,
      file(
        fileRow("Position 1", {
          label: "y",
          dose: 5,
          problems: [
            "Unknown role 'Standard'. Use Sample, Reference, Blank, Positive control or Negative control",
          ],
        }),
      ),
      OPEN,
    );
    expect(out.rows[0]).toMatchObject({ label: "y", dose: "5", wellType: "reference" });
    expect(out.problems).toEqual([
      "Position 1: Unknown role 'Standard'. Use Sample, Reference, Blank, Positive control or Negative control",
    ]);
    expect(out.filled).toBe(1);
  });

  it("fills the compound and its batch together", () => {
    const out = applyLayout(rows, file(fileRow("Position 1", { compound })), OPEN);
    expect(out.rows[0]).toMatchObject({
      moleculeId: "m9",
      moleculeName: "Compound nine",
      moleculeRef: "REG-0009",
      batchId: "b9",
      batchNumber: "B-9",
    });
  });

  it("fills the compound and leaves the batch empty when a choice is needed", () => {
    const needsChoice = {
      ...compound,
      batch_id: null,
      batch_number: null,
      needs_batch_choice: true,
    };
    const out = applyLayout(rows, file(fileRow("Position 2", { compound: needsChoice })), OPEN);
    expect(out.rows[1]).toMatchObject({
      moleculeId: "m9",
      moleculeRef: "REG-0009",
      batchId: null,
      batchNumber: null,
    });
  });

  it("keeps the batch chosen in the table when the file names its compound and no batch", () => {
    const sameCompound = {
      ...compound,
      molecule_id: "m1",
      registration_number: "REG-0001",
      batch_id: null,
      batch_number: null,
      needs_batch_choice: true,
    };
    const out = applyLayout(
      rows,
      file(fileRow("Position 2", { compound: sameCompound, dose: 20 })),
      OPEN,
    );
    expect(out.rows[1]).toMatchObject({ moleculeId: "m1", batchId: "b1", batchNumber: "B-1" });
    expect(out.rows[1].dose).toBe("20");
  });

  it("sets used from the Use column in the wizard", () => {
    const out = applyLayout(
      rows,
      file(fileRow("Position 1", { use: false }), fileRow("Position 3", { use: true })),
      OPEN,
    );
    expect(out.rows.map((r) => r.used)).toEqual([false, true, true]);
    expect(out.filled).toBe(2);
  });

  it("treats Use = No as a problem that changes nothing when positions cannot be removed", () => {
    const closed = { allowUse: false, calculatedLocked: false };
    const out = applyLayout(
      rows,
      file(
        fileRow("Position 1", { use: false, label: "y" }),
        fileRow("Position 2", { use: true, label: "z" }),
      ),
      closed,
    );
    expect(out.rows[0]).toBe(rows[0]);
    expect(out.rows[1]).toMatchObject({ used: true, label: "z" });
    expect(out.problems).toEqual([
      "Position 1: positions cannot be removed here. For a draft or in-progress run, reset all run data and import again. Otherwise, import into a new run.",
    ]);
    expect(out.filled).toBe(1);
  });

  it("ignores role, compound, batch and concentration with one notice when they are locked", () => {
    const locked = { allowUse: false, calculatedLocked: true };
    const out = applyLayout(
      rows,
      {
        ...file(
          fileRow("Position 1", { well_type: "sample", compound, label: "y" }),
          fileRow("Position 2", { dose: 99 }),
        ),
        calculated_columns_ignored: true,
      },
      locked,
    );
    expect(out.rows[0]).toEqual({ ...rows[0], label: "y" });
    expect(out.rows[1]).toBe(rows[1]);
    expect(out.notices).toEqual([
      "Role, Compound, Batch and Concentration in the file were ignored: they can be changed only while the run is draft or in progress.",
    ]);
    expect(out.filled).toBe(1);
  });

  it("says the locked columns were ignored even when none of their cells could be read", () => {
    const locked = { allowUse: false, calculatedLocked: true };
    // The server read Role "Standard" and Compound "NOPE": no value, no problem on a locked run.
    const out = applyLayout(
      rows,
      { ...file(fileRow("Position 1", { label: "y" })), calculated_columns_ignored: true },
      locked,
    );
    expect(out.notices).toEqual([
      "Role, Compound, Batch and Concentration in the file were ignored: they can be changed only while the run is draft or in progress.",
    ]);
    expect(out.problems).toEqual([]);
  });

  it("reports unrecognised columns as a notice", () => {
    const out = applyLayout(
      rows,
      { rows: [], unrecognised_columns: ["Plate", "Well"], calculated_columns_ignored: false },
      OPEN,
    );
    expect(out.notices).toEqual(["Columns not recognized and ignored: Plate, Well"]);
  });
});

describe("cells a spreadsheet would read as formulas", () => {
  const risky: LabellingRow[] = [
    { ...rows[0], label: "=1+1", note: "@sum" },
    { ...rows[1], dose: "-5" },
  ];
  const lines = () => layoutTemplateCsv(risky, { doseUnit: "µM", withUse: false }).split("\r\n");

  it("writes a label and a note that start a formula with a leading apostrophe", () => {
    expect(lines()[1]).toBe("Position 1,'=1+1,Reference,,,,'@sum");
  });

  it("prefixes a concentration that starts a formula too, but not an ordinary label", () => {
    expect(lines()[2]).toBe("Position 2,x,Sample,REG-0001,B-1,'-5,");
  });

  it("applies the values as the server read them: the server drops the apostrophe", () => {
    const fromFile = file(fileRow("Position 1", { label: "=1+1", note: "@sum" }));
    expect(applyLayout(risky, fromFile, OPEN)).toMatchObject({ filled: 0, problems: [] });
    // A value the server left an apostrophe on is the user's own; it stays.
    const out = applyLayout(rows, file(fileRow("Position 1", { label: "'=x" })), OPEN);
    expect(out.rows[0].label).toBe("'=x");
  });
});

describe("match from labels", () => {
  const empty = rows[0];
  const labelled = (key: string, label: string, values: Partial<LabellingRow> = {}) => ({
    ...empty,
    key,
    positionLabel: `Position ${key}`,
    label,
    ...values,
  });
  const table: LabellingRow[] = [
    labelled("1", "SACC-0000001"),
    labelled("2", " SACC-0000002 "),
    labelled("3", "DMSO"),
    labelled("4", "SACC-0000001"),
    labelled("5", "SACC-0000001", { moleculeId: "m1", moleculeName: "Kept", batchId: "b1" }),
    labelled("6", "   "),
    labelled("7", "SACC-0000007", { used: false }),
    labelled("8", "x".repeat(201)),
  ];
  const needsChoice = { ...compound, batch_id: null, batch_number: null, needs_batch_choice: true };
  const answer = {
    matches: [
      { label: "SACC-0000001", compound },
      { label: "SACC-0000002", compound: needsChoice },
      { label: "DMSO", compound: null },
    ],
  };

  it("asks once about each label of a used position that has a label and no compound", () => {
    expect(labelsToMatch(table)).toEqual(["SACC-0000001", "SACC-0000002", "DMSO"]);
    expect(labelsToMatch(rows)).toEqual(["Protein alone, buffer"]);
    expect(labelsToMatch([table[4], table[5], table[6], table[7]])).toEqual([]);
  });

  it("fills the positions whose label matched, as a layout file naming the compound would", () => {
    const out = applyLabelMatches(table, answer);
    expect(out.matched).toBe(3);
    for (const i of [0, 3]) {
      expect(out.rows[i]).toEqual({
        ...table[i],
        moleculeId: "m9",
        moleculeName: "Compound nine",
        moleculeRef: "REG-0009",
        batchId: "b9",
        batchNumber: "B-9",
      });
    }
    // Several batches: the compound is filled and the batch is left to choose.
    expect(out.rows[1]).toMatchObject({ moleculeId: "m9", batchId: null, batchNumber: null });
    expect(out.rows[1].label).toBe(" SACC-0000002 ");
  });

  it("leaves a position that has a compound, no label or is unused exactly as it is", () => {
    const out = applyLabelMatches(table, {
      matches: [...answer.matches, { label: "SACC-0000007", compound }],
    });
    for (const i of [2, 4, 5, 6, 7]) expect(out.rows[i]).toBe(table[i]);
  });

  it("lists each label that named no compound once, in table order", () => {
    const twice = [...table, labelled("9", "160 CoA"), labelled("10", "DMSO")];
    const out = applyLabelMatches(twice, {
      matches: [...answer.matches, { label: "160 CoA", compound: null }],
    });
    expect(out.unmatched).toEqual(["DMSO", "160 CoA"]);
  });

  it("changes nothing when no label matched", () => {
    const out = applyLabelMatches(table, { matches: [{ label: "DMSO", compound: null }] });
    expect(out).toMatchObject({ matched: 0, unmatched: ["DMSO"] });
    expect(out.rows).toEqual(table);
  });

  it("applies the answer to the table as it is now: a compound chosen or a label edited meanwhile stays", () => {
    const now = [
      { ...table[0], moleculeId: "m2", moleculeName: "Chosen by hand" },
      { ...table[1], label: "edited" },
      table[3],
    ];
    const out = applyLabelMatches(now, answer);
    expect(out.matched).toBe(1);
    expect(out.rows[0]).toBe(now[0]);
    expect(out.rows[1]).toBe(now[1]);
    expect(out.rows[2].moleculeId).toBe("m9");
    expect(out.unmatched).toEqual([]);
  });
});
