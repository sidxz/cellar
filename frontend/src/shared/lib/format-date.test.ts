import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatDate, formatDateTime, formatRelativeDate, formatRelativeDay } from "./format-date";

describe("formatDate", () => {
  it("formats a Date object", () => {
    // Use noon local-time to avoid midnight UTC crossing into the previous day
    const d = new Date(2026, 4, 12, 12, 0, 0); // May 12 2026 noon local
    expect(formatDate(d)).toMatch(/May\s+12,\s+2026/);
  });

  it("formats an ISO string", () => {
    // noon local-time → always Jan 1 regardless of timezone
    const d = new Date(2024, 0, 1, 12, 0, 0);
    expect(formatDate(d)).toMatch(/Jan\s+1,\s+2024/);
  });

  it("returns empty string for null", () => {
    expect(formatDate(null)).toBe("");
  });

  it("returns empty string for undefined", () => {
    expect(formatDate(undefined)).toBe("");
  });
});

describe("formatDateTime", () => {
  it("formats a Date object with time", () => {
    // Pin to a known UTC instant — local timezone may shift hours but year/month/day must match
    const result = formatDateTime(new Date("2026-05-12T00:00:00Z"));
    expect(result).toMatch(/2026/);
    expect(result).toMatch(/May/);
  });

  it("formats an ISO string with time", () => {
    const result = formatDateTime("2024-06-15T14:30:00Z");
    expect(result).toMatch(/2024/);
    expect(result).toMatch(/Jun/);
  });

  it("returns empty string for null", () => {
    expect(formatDateTime(null)).toBe("");
  });

  it("returns empty string for undefined", () => {
    expect(formatDateTime(undefined)).toBe("");
  });
});

describe("formatRelativeDate", () => {
  const NOW = new Date("2026-05-12T12:00:00Z").getTime();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for timestamps < 60 s ago', () => {
    const input = new Date(NOW - 30 * 1000);
    expect(formatRelativeDate(input)).toBe("just now");
  });

  it('returns "Xm ago" for timestamps < 60 m ago', () => {
    const input = new Date(NOW - 5 * 60 * 1000);
    expect(formatRelativeDate(input)).toBe("5m ago");
  });

  it('returns "Xh ago" for timestamps < 24 h ago', () => {
    const input = new Date(NOW - 3 * 60 * 60 * 1000);
    expect(formatRelativeDate(input)).toBe("3h ago");
  });

  it('returns "yesterday" for timestamps 24-48 h ago', () => {
    const input = new Date(NOW - 36 * 60 * 60 * 1000);
    expect(formatRelativeDate(input)).toBe("yesterday");
  });

  it('returns "Xd ago" for timestamps < 14 d ago', () => {
    const input = new Date(NOW - 5 * 24 * 60 * 60 * 1000);
    expect(formatRelativeDate(input)).toBe("5d ago");
  });

  it('returns "Xw ago" for timestamps < 8 w ago', () => {
    const input = new Date(NOW - 3 * 7 * 24 * 60 * 60 * 1000);
    expect(formatRelativeDate(input)).toBe("3w ago");
  });

  it("falls back to formatDate for old dates", () => {
    const input = new Date(NOW - 100 * 24 * 60 * 60 * 1000);
    const result = formatRelativeDate(input);
    expect(result).toMatch(/\d{4}/); // contains a year
    expect(result).not.toMatch(/ago/);
  });

  it("returns empty string for null", () => {
    expect(formatRelativeDate(null)).toBe("");
  });
});

describe("formatRelativeDay", () => {
  // Pin to a fixed *local* noon so date-only strings (parsed at local midnight)
  // resolve to deterministic day offsets regardless of the runner's timezone.
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 4, 12, 12, 0, 0)); // May 12 2026, local noon
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "today" for the current day', () => {
    expect(formatRelativeDay("2026-05-12")).toBe("today");
  });

  it('returns "today" for a future date (clamped)', () => {
    expect(formatRelativeDay("2026-05-20")).toBe("today");
  });

  it('returns "yesterday" for the prior day', () => {
    expect(formatRelativeDay("2026-05-11")).toBe("yesterday");
  });

  it('returns "Xd ago" within two weeks', () => {
    expect(formatRelativeDay("2026-05-07")).toBe("5d ago");
  });

  it('returns "Xw ago" within ~two months', () => {
    expect(formatRelativeDay("2026-04-12")).toBe("4w ago");
  });

  it("falls back to a calendar date omitting the year in the current year", () => {
    const result = formatRelativeDay("2026-01-01");
    expect(result).toMatch(/Jan\s+1/);
    expect(result).not.toMatch(/2026/);
    expect(result).not.toMatch(/ago/);
  });

  it("includes the year for a different-year fallback", () => {
    const result = formatRelativeDay("2024-01-01");
    expect(result).toMatch(/Jan\s+1,\s+2024/);
  });

  it("returns empty string for null", () => {
    expect(formatRelativeDay(null)).toBe("");
  });

  it("returns empty string for an unparseable value", () => {
    expect(formatRelativeDay("not-a-date")).toBe("");
  });
});
