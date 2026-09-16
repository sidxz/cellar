import { describe, expect, it } from "vitest";
import { isTerminalImportStatus } from "./job-status";

describe("isTerminalImportStatus", () => {
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
