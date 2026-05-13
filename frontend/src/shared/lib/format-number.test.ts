import { describe, expect, it } from "vitest";
import { formatFileSize } from "./format-number";

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
