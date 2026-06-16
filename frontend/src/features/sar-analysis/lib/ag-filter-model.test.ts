import { describe, expect, it } from "vitest";
import { agFilterModelToParam, colIdToBackendKey } from "./ag-filter-model";

describe("colIdToBackendKey", () => {
  it("maps physchem + activity + reg# + R-group col ids", () => {
    expect(colIdToBackendKey("mw")).toBe("molecular_weight");
    expect(colIdToBackendKey("clogp")).toBe("logp");
    expect(colIdToBackendKey("tpsa")).toBe("tpsa");
    expect(colIdToBackendKey("activity:value")).toBe("activity");
    expect(colIdToBackendKey("registration_number")).toBe("registration_number");
    expect(colIdToBackendKey("rg:R1")).toBe("R1");
    expect(colIdToBackendKey("structure")).toBeNull(); // not sortable/filterable
  });
});

describe("agFilterModelToParam", () => {
  it("maps a text 'contains' filter", () => {
    const out = agFilterModelToParam({
      "registration_number": { filterType: "text", type: "contains", filter: "CV" },
    });
    expect(out).toEqual({ registration_number: { kind: "text", op: "contains", value: "CV" } });
  });

  it("maps a number 'greaterThan' filter on physchem", () => {
    const out = agFilterModelToParam({ mw: { filterType: "number", type: "greaterThan", filter: 200 } });
    expect(out).toEqual({ molecular_weight: { kind: "number", op: "gt", value: 200 } });
  });

  it("maps inRange to between with value2", () => {
    const out = agFilterModelToParam({
      tpsa: { filterType: "number", type: "inRange", filter: 20, filterTo: 80 },
    });
    expect(out).toEqual({ tpsa: { kind: "number", op: "between", value: 20, value2: 80 } });
  });

  it("maps an R-group equals filter to the bare label key", () => {
    const out = agFilterModelToParam({ "rg:R1": { filterType: "text", type: "equals", filter: "F" } });
    expect(out).toEqual({ R1: { kind: "text", op: "eq", value: "F" } });
  });

  it("drops unknown columns, unsupported ops, and blank filters", () => {
    expect(
      agFilterModelToParam({
        nope: { filterType: "text", type: "contains", filter: "x" },
        mw: { filterType: "number", type: "blank", filter: null },
      }),
    ).toBeUndefined();
    expect(agFilterModelToParam(null)).toBeUndefined();
    expect(agFilterModelToParam({})).toBeUndefined();
  });
});
