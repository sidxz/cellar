import { describe, expect, it } from "vitest";
import { serverSortToken } from "./search-sort";

describe("serverSortToken", () => {
  it.each([
    ["molecule", "registration_number"],
    ["similarity", "similarity"],
    ["lifecycle_stage", "lifecycle_stage"],
    ["prop:molecular_weight", "molecular_weight"],
    ["any", "any"],
    ["drc:rd1:value", "drc:rd1"],
    ["drc:rd1:value@cond:10 µM", "drc:rd1@cond:10 µM"],
    ["drc:rd1:ic:50", "drc:rd1:ic:50"],
    ["drc:rd1:ec:90@run:r1", "drc:rd1:ec:90@run:r1"],
    ["rd:p1:rd2", "rd:p1:rd2"],
    ["rd:p1:rd2:percent_inhibition@cond:", "rd:p1:rd2:percent_inhibition@cond:"],
  ])("%s sorts on the server as %s", (colId, token) => {
    expect(serverSortToken(colId)).toBe(token);
  });

  it.each([
    "smiles",
    "inchi_key",
    "drc:rd1:plot",
    "drc:rd1:plot@cond:1 mM",
    "p1:no-runs",
    undefined,
  ])("%s is not sortable", (colId) => {
    expect(serverSortToken(colId)).toBeNull();
  });
});
