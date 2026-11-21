import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type AppConfig, AppConfigProvider } from "@/shared/lib/app-config";
import type { CampaignResponse } from "../../types";
import { HeaderStrip } from "./header-strip";

vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => true }));
vi.mock("@/features/screening-assay/components/target-chips", () => ({ TargetChips: () => null }));
vi.mock("@/features/tagging/components/tag-chips", () => ({ TagChips: () => null }));
vi.mock("../../hooks/use-release-campaign", () => ({
  useReleaseCampaign: () => ({ mutate: vi.fn(), isPending: false }),
}));

const base = {
  id: "c1",
  name: "Round 1",
  status: "draft",
  description: "Primary screen",
  channels: [],
  results: [],
  targets: [],
} as unknown as CampaignResponse;
const managed = {
  ...base,
  managed_by: "daikon",
  managed_url: "http://localhost:3002/screens/S1",
  managed_label: "Daikon",
} as CampaignResponse;

function renderHeader(campaign: CampaignResponse) {
  const config = { returnOrigins: [] } as unknown as AppConfig;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AppConfigProvider config={config}>
        <HeaderStrip
          campaign={campaign}
          isDraft
          onRefresh={() => {}}
          onPreview={() => {}}
          onClose={() => {}}
        />
      </AppConfigProvider>
    </QueryClientProvider>,
  );
}

describe("HeaderStrip", () => {
  it("offers Refresh and Close on a draft ChemCellar manages", () => {
    renderHeader(base);
    expect(screen.getByRole("button", { name: /Close/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeInTheDocument();
    expect(screen.queryByText(/Locked by/)).not.toBeInTheDocument();
  });

  it("says who manages the campaign and leaves its lifecycle to that app", () => {
    renderHeader(managed);
    expect(screen.getByText("Locked by Daikon")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Close$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Refresh/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preview DAIKON export/ })).toBeInTheDocument();
  });
});
