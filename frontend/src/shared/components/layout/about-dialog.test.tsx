import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { AboutDialog } from "./about-dialog";

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

function renderDialog() {
  const config = {
    apiUrl: "",
    appUrl: "",
    sentinelUrl: "",
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
        <AboutDialog open onOpenChange={vi.fn()} />
      </AppConfigProvider>
    </QueryClientProvider>,
  );
}

describe("AboutDialog", () => {
  it("shows UI and API versions", () => {
    renderDialog();
    expect(screen.getByText(/v2\.1\.0/)).toBeInTheDocument(); // UI
    expect(screen.getByText(/v1\.4\.0/)).toBeInTheDocument(); // API
    expect(screen.getByText(/84e7848/)).toBeInTheDocument(); // UI sha
    expect(screen.getByText(/1a2b3c4/)).toBeInTheDocument(); // API sha
  });
});
