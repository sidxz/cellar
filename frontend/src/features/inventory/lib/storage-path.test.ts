import { describe, expect, it } from "vitest";
import type { StorageLocation } from "../types";
import { storageChain, storageFullPath, storagePath } from "./storage-path";

const loc = (id: string, name: string, parent_id: string | null): StorageLocation =>
  ({ id, name, parent_id, type: "x", workspace_id: "w" }) as unknown as StorageLocation;
const locations = [
  loc("site", "TAMU", null),
  loc("bld", "ILSB", "site"),
  loc("room", "Room 1148", "bld"),
  loc("frz", "Freezer 3", "room"),
];

describe("storage path", () => {
  it("walks the parent chain root-first", () => {
    expect(storageChain(locations, "frz")).toEqual(["TAMU", "ILSB", "Room 1148", "Freezer 3"]);
  });
  it("storagePath keeps the last `depth` names; full path keeps all", () => {
    expect(storagePath(locations, "frz")).toBe("Room 1148 › Freezer 3");
    expect(storagePath(locations, "frz", 3)).toBe("ILSB › Room 1148 › Freezer 3");
    expect(storageFullPath(locations, "frz")).toBe("TAMU › ILSB › Room 1148 › Freezer 3");
  });
  it("unknown id / no id / no locations → empty", () => {
    expect(storagePath(locations, "nope")).toBe("");
    expect(storagePath(locations, null)).toBe("");
    expect(storagePath(undefined, "frz")).toBe("");
  });
  it("survives a parent cycle", () => {
    const cyclic = [loc("a", "A", "b"), loc("b", "B", "a")];
    expect(storageChain(cyclic, "a")).toEqual(["B", "A"]);
  });
});
