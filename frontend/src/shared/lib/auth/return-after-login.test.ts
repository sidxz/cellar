import { afterEach, describe, expect, it, vi } from "vitest";

import { rememberPlace, takePlace } from "./return-after-login";

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("return after login", () => {
  it("comes back to the page that was asked for, once", () => {
    rememberPlace("/assays?new_protocol=1&return_to=x");
    expect(takePlace()).toBe("/assays?new_protocol=1&return_to=x");
    expect(takePlace()).toBeNull();
  });

  it.each(["//evil.com", "https://evil.com", "/\\evil.com", "/\t/evil.com", "/\n/evil.com", ""])(
    "never goes to %j",
    (path) => {
      rememberPlace(path);
      expect(takePlace()).toBeNull();
    },
  );

  it("refuses a place planted in storage", () => {
    window.sessionStorage.setItem("cellar.returnAfterLogin", "//evil.com");
    expect(takePlace()).toBeNull();
  });

  it("gives no place when storage is unavailable", () => {
    vi.spyOn(window.sessionStorage, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => rememberPlace("/assays")).not.toThrow();
    expect(takePlace()).toBeNull();
  });
});
