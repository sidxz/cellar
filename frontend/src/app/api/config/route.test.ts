import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("/api/config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns baked UI build info from env", async () => {
    vi.stubEnv("APP_VERSION", "2.1.0");
    vi.stubEnv("APP_GIT_SHA", "84e7848");
    vi.stubEnv("APP_BUILD_DATE", "2026-06-17T12:00:00Z");
    vi.stubEnv("APP_ENVIRONMENT", "production");

    const body = await GET().json();

    expect(body.uiVersion).toBe("2.1.0");
    expect(body.uiGitSha).toBe("84e7848");
    expect(body.uiBuildDate).toBe("2026-06-17T12:00:00Z");
    expect(body.environment).toBe("production");
  });

  it("falls back to dev placeholders when env is absent", async () => {
    vi.stubEnv("APP_VERSION", "");
    vi.stubEnv("APP_GIT_SHA", "");
    vi.stubEnv("APP_ENVIRONMENT", "");

    const body = await GET().json();

    expect(body.uiVersion).toBe("0.0.0+dev");
    expect(body.uiGitSha).toBe("unknown");
    expect(body.environment).toBe("development");
  });
});
