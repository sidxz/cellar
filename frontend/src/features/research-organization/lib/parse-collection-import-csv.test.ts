import { describe, expect, it } from "vitest";

import {
  buildCollectionImportTemplate,
  parseCollectionImportCsv,
} from "./parse-collection-import-csv";

describe("parseCollectionImportCsv", () => {
  it("returns header row + raw rows for an arbitrary CSV", async () => {
    const csv = "Reg No.,Compound\nCC-000001,Phenol\n,Acetone\n";
    const result = await parseCollectionImportCsv(csv);
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.headers).toEqual(["Reg No.", "Compound"]);
    expect(result.rows).toEqual([
      { "Reg No.": "CC-000001", Compound: "Phenol" },
      { "Reg No.": "", Compound: "Acetone" },
    ]);
  });

  it("returns an error when CSV is empty", async () => {
    const result = await parseCollectionImportCsv("");
    expect(result.kind).toBe("error");
  });
});

describe("buildCollectionImportTemplate", () => {
  it("returns a CSV string with all six columns and example rows", () => {
    const csv = buildCollectionImportTemplate();
    const lines = csv.trim().split("\n");
    expect(lines[0]).toBe(
      "registration_number,external_id,smiles,inchi_key,name,notes",
    );
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });
});
