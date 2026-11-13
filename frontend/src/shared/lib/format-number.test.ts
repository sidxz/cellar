import { describe, expect, it } from "vitest";
import { formatCount, formatFileSize } from "./format-number";

describe("formatFileSize", () => {
  it("formats bytes", () => {
    expect(formatFileSize(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatFileSize(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("formats gigabytes", () => {
    expect(formatFileSize(2 * 1024 ** 3)).toBe("2.0 GB");
  });

  it("returns — for NaN", () => {
    expect(formatFileSize(Number.NaN)).toBe("—");
  });

  it("returns — for Infinity", () => {
    expect(formatFileSize(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("returns — for negative values", () => {
    expect(formatFileSize(-1)).toBe("—");
  });
});

describe("formatCount", () => {
  it("puts the noun in the singular for one and the plural otherwise", () => {
    expect(formatCount(1, "trace")).toBe("1 trace");
    expect(formatCount(0, "trace")).toBe("0 traces");
    expect(formatCount(3, "readout value")).toBe("3 readout values");
  });
});
