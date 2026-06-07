import { describe, expect, it } from "vitest";
import { timeAgo } from "./time-ago";

describe("timeAgo", () => {
  const now = new Date("2026-06-07T12:00:00Z").getTime();
  it("returns em dash for null/undefined", () => {
    expect(timeAgo(null, now)).toBe("—");
    expect(timeAgo(undefined, now)).toBe("—");
  });
  it("formats minutes", () => expect(timeAgo("2026-06-07T11:30:00Z", now)).toBe("30m ago"));
  it("formats hours", () => expect(timeAgo("2026-06-07T09:00:00Z", now)).toBe("3h ago"));
  it("formats days", () => expect(timeAgo("2026-06-04T12:00:00Z", now)).toBe("3d ago"));
  it("formats weeks", () => expect(timeAgo("2026-05-24T12:00:00Z", now)).toBe("2w ago"));
});
