import { describe, expect, it } from "vitest";
import { TERMINAL_IMPORT_STATUSES, isTerminalImportStatus } from "./job-status";

describe("isTerminalImportStatus", () => {
  it("is true for every terminal import status", () => {
    for (const status of TERMINAL_IMPORT_STATUSES) {
      expect(isTerminalImportStatus(status)).toBe(true);
    }
  });

  it("matches the documented terminal vocabulary exactly", () => {
    expect([...TERMINAL_IMPORT_STATUSES]).toEqual(["completed", "completed_with_errors", "failed"]);
  });

  it("is false for in-flight statuses", () => {
    expect(isTerminalImportStatus("pending")).toBe(false);
    expect(isTerminalImportStatus("processing")).toBe(false);
    expect(isTerminalImportStatus("running")).toBe(false);
  });

  it("is false for null/undefined/empty", () => {
    expect(isTerminalImportStatus(null)).toBe(false);
    expect(isTerminalImportStatus(undefined)).toBe(false);
    expect(isTerminalImportStatus("")).toBe(false);
  });
});
