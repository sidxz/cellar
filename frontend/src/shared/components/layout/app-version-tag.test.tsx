import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { AppVersionTag } from "./app-version-tag";

function renderWithConfig(uiVersion: string) {
  const config = {
    apiUrl: "",
    appUrl: "",
    sentinelUrl: "",
    idpProvider: "google",
    googleClientId: "",
    entraIdClientId: "",
    entraIdTenantId: "",
    uiVersion,
    uiGitSha: "unknown",
    uiBuildDate: "unknown",
    environment: "development",
  };
  return render(
    <AppConfigProvider config={config}>
      <AppVersionTag />
    </AppConfigProvider>,
  );
}

describe("AppVersionTag", () => {
  it("renders the UI version from config", () => {
    renderWithConfig("2.1.0");
    expect(screen.getByText("UI v2.1.0")).toBeInTheDocument();
  });
});
