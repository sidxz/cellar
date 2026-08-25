import { describe, expect, it } from "vitest";
import { shouldAutoReauth } from "./auto-reauth";

describe("shouldAutoReauth", () => {
  it("is off on the auth flow and the kiosk, on elsewhere", () => {
    expect(shouldAutoReauth("/login")).toBe(false);
    expect(shouldAutoReauth("/auth/callback")).toBe(false);
    expect(shouldAutoReauth("/kiosk")).toBe(false);
    expect(shouldAutoReauth("/kiosk/anything")).toBe(false);
    expect(shouldAutoReauth("/inventory/plates")).toBe(true);
    expect(shouldAutoReauth(null)).toBe(false);
  });
});
