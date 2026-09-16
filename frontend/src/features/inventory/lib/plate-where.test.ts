import { describe, expect, it } from "vitest";
import type { PlateLoan, PlateLoanItem } from "../hooks/use-plate-loans";
import type { StorageLocation } from "../types";
import type { RegisteredPlate } from "../types/plates";
import { plateChipKeys, plateWhereabouts, whereText } from "./plate-where";

const plate = (over: Partial<RegisteredPlate> = {}): RegisteredPlate =>
  ({
    id: "p1",
    barcode: "0001",
    plate_label: "P1",
    format: "384",
    plate_type: "assay",
    status: "stored",
    storage_location_id: "frz",
    workspace_id: "w",
    registered_by: "u",
    ...over,
  }) as unknown as RegisteredPlate;
const locations = [
  { id: "room", name: "Room 1148", parent_id: null },
  { id: "frz", name: "Freezer 3", parent_id: "room" },
] as unknown as StorageLocation[];
const custody = (itemStatus: string, due: string | null) => ({
  loan: {
    id: "l1",
    status: "open",
    requested_by: "u1",
    due_date: due,
    items: [],
  } as unknown as PlateLoan,
  item: { id: "i1", plate_id: "p1", status: itemStatus } as unknown as PlateLoanItem,
});
const name = () => "Maia Young";

describe("plateWhereabouts precedence", () => {
  it("custody beats everything", () => {
    const w = plateWhereabouts(
      plate({ status: "depleted" }),
      custody("checked_out", "2000-01-01"),
      locations,
    );
    expect(w.kind).toBe("custody");
    expect(w.kind === "custody" && w.overdue).toBe(true);
  });
  it("terminal status beats location", () => {
    expect(plateWhereabouts(plate({ status: "disposed" }), undefined, locations)).toEqual({
      kind: "terminal",
      status: "disposed",
    });
  });
  it("location, else status", () => {
    expect(plateWhereabouts(plate(), undefined, locations)).toEqual({
      kind: "location",
      path: "Room 1148 › Freezer 3",
      heroPath: "Room 1148 › Freezer 3",
      fullPath: "Room 1148 › Freezer 3",
    });
    expect(plateWhereabouts(plate({ storage_location_id: null }), undefined, locations)).toEqual({
      kind: "status",
      status: "stored",
    });
  });
});

describe("whereText", () => {
  it("checked out with a due date → name · due phrase, overdue tone", () => {
    const t = whereText(
      plateWhereabouts(plate(), custody("checked_out", "2000-01-01"), locations),
      name,
    );
    expect(t.text).toMatch(/^Maia Young · \d+ y overdue$/);
    expect(t.tone).toBe("overdue");
  });
  it("other custody statuses → name · status word, loan tone", () => {
    const t = whereText(plateWhereabouts(plate(), custody("requested", null), locations), name);
    expect(t).toEqual({ text: "Maia Young · requested", tone: "loan", title: undefined });
  });
  it("terminal muted; location normal with full-path title; status muted", () => {
    expect(whereText({ kind: "terminal", status: "depleted" }, name)).toEqual({
      text: "Depleted",
      tone: "muted",
    });
    expect(
      whereText(
        {
          kind: "location",
          path: "Freezer 3",
          heroPath: "Room › Freezer 3",
          fullPath: "Room › Freezer 3",
        },
        name,
      ),
    ).toEqual({ text: "Freezer 3", tone: "normal", title: "Room › Freezer 3" });
    expect(whereText({ kind: "status", status: "registered" }, name)).toEqual({
      text: "Registered",
      tone: "muted",
    });
  });
});

describe("plateChipKeys", () => {
  it("on_loan (+overdue) for custody; depleted for depleted plates", () => {
    const w = plateWhereabouts(plate(), custody("checked_out", "2000-01-01"), locations);
    expect([...plateChipKeys(plate(), w)].sort()).toEqual(["on_loan", "overdue"]);
    expect([
      ...plateChipKeys(plate({ status: "depleted" }), { kind: "terminal", status: "depleted" }),
    ]).toEqual(["depleted"]);
    expect(plateChipKeys(plate(), { kind: "status", status: "stored" }).size).toBe(0);
  });
});
