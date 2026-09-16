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
    vi.stubEnv("APP_ENV", "production");

    const body = await GET().json();

    expect(body.uiVersion).toBe("2.1.0");
    expect(body.uiGitSha).toBe("84e7848");
    expect(body.uiBuildDate).toBe("2026-06-17T12:00:00Z");
    expect(body.environment).toBe("production");
  });

  it("falls back to dev placeholders when env is absent", async () => {
    vi.stubEnv("APP_VERSION", "");
    vi.stubEnv("APP_GIT_SHA", "");
    vi.stubEnv("APP_ENV", "");

    const body = await GET().json();

    expect(body.uiVersion).toBe("0.0.0+dev");
    expect(body.uiGitSha).toBe("unknown");
    expect(body.environment).toBe("development");
  });

  it("exposes the prot-cellar UI url with a dev default", async () => {
    vi.stubEnv("APP_PROT_CELLAR_URL", "");
    expect((await GET().json()).protCellarUrl).toBe("http://localhost:3001");

    vi.stubEnv("APP_PROT_CELLAR_URL", "https://prot-cellar.example");
    expect((await GET().json()).protCellarUrl).toBe("https://prot-cellar.example");
  });
});
