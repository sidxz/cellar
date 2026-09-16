import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import SettingsPage from "./page";

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme: vi.fn() }),
}));

vi.mock("@/shared/hooks/use-api-version", () => ({
  useApiVersion: () => ({
    data: {
      name: "cellar-backend",
      version: "1.4.0",
      git_sha: "1a2b3c4",
      build_date: "2026-06-16",
      environment: "production",
    },
    isLoading: false,
    isError: false,
  }),
}));

function renderPage() {
  const config = {
    apiUrl: "",
    appUrl: "",
    duarUrl: "",
    protCellarUrl: "",
    idpProvider: "google",
    googleClientId: "",
    entraIdClientId: "",
    entraIdTenantId: "",
    uiVersion: "2.1.0",
    uiGitSha: "84e7848",
    uiBuildDate: "2026-06-17",
    environment: "production",
  };
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AppConfigProvider config={config}>
        <SettingsPage />
      </AppConfigProvider>
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    useFontFamilyStore.setState({ font: "plex" });
  });

  it("shows appearance controls and build identity", () => {
    renderPage();
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText(/v2\.1\.0/)).toBeInTheDocument(); // UI version
    expect(screen.getByText(/v1\.4\.0/)).toBeInTheDocument(); // API version
    expect(screen.getByText(/84e7848/)).toBeInTheDocument(); // UI sha
  });

  it("switches the font family store", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Inter" }));
    expect(useFontFamilyStore.getState().font).toBe("inter");
    expect(screen.getByRole("button", { name: "Inter" })).toHaveAttribute("aria-pressed", "true");
  });
});
