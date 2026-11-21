import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type AppConfig, AppConfigProvider } from "@/shared/lib/app-config";
import type { CampaignResponse } from "../../types";
import { ManagedByBanner } from "./managed-by-banner";

const state = vi.hoisted(() => ({ admin: false, release: vi.fn() }));
afterEach(() => {
  state.admin = false;
  state.release.mockReset();
});
vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: (role: string) => (role === "admin" ? state.admin : true),
}));
vi.mock("../../hooks/use-release-campaign", () => ({
  useReleaseCampaign: () => ({ mutate: state.release, isPending: false }),
}));

const ROUND = "http://localhost:3002/screens/S1?round=R1";
const campaign = (url = ROUND) =>
  ({
    id: "c1",
    managed_by: "daikon",
    managed_url: url,
    managed_label: "Daikon",
  }) as unknown as CampaignResponse;
const config = {
  returnOrigins: [{ label: "Daikon", origin: "http://localhost:3002" }],
} as AppConfig;

function renderBanner(c: CampaignResponse) {
  return render(
    <AppConfigProvider config={config}>
      <ManagedByBanner campaign={c} />
    </AppConfigProvider>,
  );
}

describe("ManagedByBanner", () => {
  it("says only that the campaign is locked by the other app", () => {
    renderBanner(campaign());
    expect(screen.getByText("Locked by Daikon")).toBeInTheDocument();
    expect(screen.queryByText(/Managed by/)).not.toBeInTheDocument();
    expect(screen.queryByText(/stages, runs, columns/)).not.toBeInTheDocument();
  });

  it("links to the round when its address is trusted", () => {
    renderBanner(campaign());
    expect(screen.getByRole("link", { name: /Open in Daikon/ })).toHaveAttribute("href", ROUND);
  });

  it("offers no link to an address it does not trust", () => {
    renderBanner(campaign("http://localhost:3002.evil.com/screens/S1"));
    expect(screen.queryByRole("link", { name: /Open in Daikon/ })).not.toBeInTheDocument();
    expect(screen.getByText("Locked by Daikon")).toBeInTheDocument();
  });

  it("offers release only to workspace admins", () => {
    renderBanner(campaign());
    expect(screen.queryByRole("button", { name: /Release from Daikon/ })).not.toBeInTheDocument();
  });

  it("releases with the reason an admin gives, and not without one", () => {
    state.admin = true;
    renderBanner(campaign());
    fireEvent.click(screen.getByRole("button", { name: /Release from Daikon/ }));
    const release = screen.getByRole("button", { name: "Release" });
    expect(release).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: /Reason/ }), {
      target: { value: "round abandoned" },
    });
    fireEvent.click(release);
    expect(state.release).toHaveBeenCalledWith(
      { campaignId: "c1", reason: "round abandoned" },
      expect.anything(),
    );
  });
});
