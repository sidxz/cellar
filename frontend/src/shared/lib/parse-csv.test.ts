import { describe, expect, it } from "vitest";

import { parseCsv } from "./parse-csv";

describe("parseCsv", () => {
  it("returns header row + row objects for a simple CSV", async () => {
    const result = await parseCsv("Reg No.,Compound\nCC-000001,Phenol\n,Acetone\n");
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.headers).toEqual(["Reg No.", "Compound"]);
    expect(result.rows).toEqual([
      { "Reg No.": "CC-000001", Compound: "Phenol" },
      { "Reg No.": "", Compound: "Acetone" },
    ]);
  });

  it("handles quoted fields containing commas (the naive-parser failure case)", async () => {
    const result = await parseCsv(
      'identifier,type\n"Acetic acid, glacial",name\nCC-1,registration_number\n',
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.rows).toEqual([
      { identifier: "Acetic acid, glacial", type: "name" },
      { identifier: "CC-1", type: "registration_number" },
    ]);
  });

  it("handles CRLF line endings", async () => {
    const result = await parseCsv("a,b\r\n1,2\r\n");
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.rows).toEqual([{ a: "1", b: "2" }]);
  });

  it("trims cell values and fills missing cells with empty strings", async () => {
    const result = await parseCsv("a,b\n  x  ,\n");
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.rows).toEqual([{ a: "x", b: "" }]);
  });

  it("returns an error when the source is empty", async () => {
    const result = await parseCsv("");
    expect(result.kind).toBe("error");
  });
});
