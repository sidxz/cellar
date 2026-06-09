import { describe, expect, it } from "vitest";
import type { ConditionDefinition } from "../types";
import {
  type ConditionColumnSpec,
  buildConditionsPayload,
  deriveConditionColumns,
  editableConditionDefs,
  formatConditionEntries,
  parseConditionValue,
  readConditionCell,
  seedConditionValues,
} from "./conditions";

const def = (over: Partial<ConditionDefinition> & { name: string }): ConditionDefinition => ({
  id: over.id ?? over.name,
  name: over.name,
  data_type: over.data_type ?? "text",
  unit: over.unit ?? null,
  pick_list_values: over.pick_list_values ?? null,
});

// ─── parseConditionValue ───────────────────────────────────────────────────────

describe("parseConditionValue", () => {
  it("strips a trailing declared unit", () => {
    expect(parseConditionValue("10 uM", "uM")).toBe("10");
  });

  it("is a no-op when no unit is declared", () => {
    expect(parseConditionValue("10 uM", null)).toBe("10 uM");
    expect(parseConditionValue("glucose", undefined)).toBe("glucose");
  });

  it("is a no-op when the value does not end with the unit", () => {
    expect(parseConditionValue("10", "uM")).toBe("10");
    expect(parseConditionValue("10 mM", "uM")).toBe("10 mM");
  });
});

// ─── buildConditionsPayload ────────────────────────────────────────────────────

describe("buildConditionsPayload", () => {
  it("appends the declared unit to bare values", () => {
    const defs = [
      def({ name: "ATP", data_type: "numeric", unit: "uM" }),
      def({ name: "Cell Line" }),
    ];
    expect(buildConditionsPayload(defs, { ATP: "10", "Cell Line": "HeLa" })).toEqual({
      ATP: "10 uM",
      "Cell Line": "HeLa",
    });
  });

  it("skips empty / whitespace-only values", () => {
    const defs = [def({ name: "ATP", unit: "uM" }), def({ name: "Cell Line" })];
    expect(buildConditionsPayload(defs, { ATP: "  ", "Cell Line": "HeLa" })).toEqual({
      "Cell Line": "HeLa",
    });
  });

  it("returns null when nothing is recorded", () => {
    const defs = [def({ name: "ATP", unit: "uM" })];
    expect(buildConditionsPayload(defs, { ATP: "" })).toBeNull();
    expect(buildConditionsPayload([], {})).toBeNull();
  });

  it("is idempotent when the value already carries the unit", () => {
    const defs = [def({ name: "ATP", unit: "uM" })];
    expect(buildConditionsPayload(defs, { ATP: "10 uM" })).toEqual({ ATP: "10 uM" });
  });
});

// ─── formatConditionEntries ────────────────────────────────────────────────────

describe("formatConditionEntries", () => {
  it("returns [] for null/empty", () => {
    expect(formatConditionEntries(null)).toEqual([]);
    expect(formatConditionEntries(undefined)).toEqual([]);
    expect(formatConditionEntries({})).toEqual([]);
  });

  it("flattens entries and stringifies non-string values", () => {
    expect(formatConditionEntries({ ATP: "10 uM", count: 3 })).toEqual([
      { key: "ATP", value: "10 uM" },
      { key: "count", value: "3" },
    ]);
  });

  it("drops null/blank values", () => {
    expect(formatConditionEntries({ a: "", b: null, c: "x" })).toEqual([{ key: "c", value: "x" }]);
  });
});

// ─── editableConditionDefs ─────────────────────────────────────────────────────

describe("editableConditionDefs", () => {
  it("appends run-only keys as synthetic text fields after the declared ones", () => {
    const defs = [def({ name: "ATP", unit: "uM" })];
    const result = editableConditionDefs(defs, { ATP: "10 uM", description: "from CDD" });
    expect(result.map((d) => d.name)).toEqual(["ATP", "description"]);
    const extra = result[1];
    expect(extra.data_type).toBe("text");
    expect(extra.unit).toBeNull();
    expect(extra.id).toContain("description");
  });

  it("does not duplicate keys already declared", () => {
    const defs = [def({ name: "ATP", unit: "uM" })];
    const result = editableConditionDefs(defs, { ATP: "10 uM" });
    expect(result).toHaveLength(1);
  });
});

// ─── seedConditionValues ───────────────────────────────────────────────────────

describe("seedConditionValues", () => {
  it("strips declared units and passes extras through", () => {
    const defs = [def({ name: "ATP", unit: "uM" }), def({ name: "Cell Line" })];
    expect(
      seedConditionValues(defs, { ATP: "10 uM", "Cell Line": "HeLa", description: "note" }),
    ).toEqual({
      ATP: "10",
      "Cell Line": "HeLa",
      description: "note",
    });
  });

  it("round-trips through buildConditionsPayload", () => {
    const defs = [def({ name: "ATP", unit: "uM" })];
    const stored = { ATP: "10 uM" };
    const seeded = seedConditionValues(defs, stored);
    expect(buildConditionsPayload(defs, seeded)).toEqual(stored);
  });
});

// ─── deriveConditionColumns ────────────────────────────────────────────────────

describe("deriveConditionColumns", () => {
  it("returns [] for no runs or no recorded conditions", () => {
    expect(deriveConditionColumns(undefined, [])).toEqual([]);
    expect(deriveConditionColumns([], [])).toEqual([]);
    expect(deriveConditionColumns([{ conditions: null }, { conditions: {} }], [])).toEqual([]);
  });

  it("emits a column only for conditions present in at least one run", () => {
    const defs = [
      def({ name: "Strain" }),
      def({ name: "ATP", data_type: "numeric", unit: "uM" }),
      def({ name: "Carbon Source" }), // declared but never used → excluded
    ];
    const runs = [
      { conditions: { Strain: "H37Rv", ATP: "10 uM" } },
      { conditions: { Strain: "H37Ra" } },
    ];
    const cols = deriveConditionColumns(runs, defs);
    expect(cols.map((c) => c.key)).toEqual(["Strain", "ATP"]);
    expect(cols.find((c) => c.key === "ATP")?.type).toBe("numeric");
    expect(cols.find((c) => c.key === "ATP")?.unit).toBe("uM");
    expect(cols.find((c) => c.key === "Strain")?.type).toBe("text");
  });

  it("appends undeclared run keys as text columns after the declared ones", () => {
    const defs = [def({ name: "Strain" })];
    const runs = [{ conditions: { Strain: "H37Rv", description: "imported" } }];
    const cols = deriveConditionColumns(runs, defs);
    expect(cols.map((c) => c.key)).toEqual(["Strain", "description"]);
    expect(cols[1]).toMatchObject({ type: "text", unit: null });
  });

  it("keeps declared order regardless of run insertion order", () => {
    const defs = [def({ name: "A" }), def({ name: "B" }), def({ name: "C" })];
    const runs = [{ conditions: { C: "3", A: "1" } }, { conditions: { B: "2" } }];
    expect(deriveConditionColumns(runs, defs).map((c) => c.key)).toEqual(["A", "B", "C"]);
  });
});

// ─── readConditionCell ─────────────────────────────────────────────────────────

describe("readConditionCell", () => {
  const numeric: ConditionColumnSpec = { key: "ATP", label: "ATP", unit: "uM", type: "numeric" };
  const text: ConditionColumnSpec = { key: "Strain", label: "Strain", unit: null, type: "text" };

  it("parses numeric columns to a number, stripping the unit", () => {
    expect(readConditionCell({ ATP: "10 uM" }, numeric)).toBe(10);
    expect(readConditionCell({ ATP: "2.5 uM" }, numeric)).toBe(2.5);
  });

  it("returns null for missing or non-numeric numeric values", () => {
    expect(readConditionCell({}, numeric)).toBeNull();
    expect(readConditionCell(null, numeric)).toBeNull();
    expect(readConditionCell({ ATP: "n/a" }, numeric)).toBeNull();
  });

  it("returns the raw string for text columns", () => {
    expect(readConditionCell({ Strain: "H37Rv" }, text)).toBe("H37Rv");
    expect(readConditionCell({ Strain: "  " }, text)).toBeNull();
    expect(readConditionCell({}, text)).toBeNull();
  });
});
