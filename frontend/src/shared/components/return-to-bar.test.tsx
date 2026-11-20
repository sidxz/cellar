import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type AppConfig, AppConfigProvider } from "@/shared/lib/app-config";
import { ReturnToBar, ReturnToBarFromUrl } from "./return-to-bar";

const state = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => state.params }));

const target = { label: "Daikon", url: "https://d.org/screens/7?round=2" };

describe("ReturnToBar", () => {
  it("offers the way back without a protocol", () => {
    render(<ReturnToBar target={target} />);
    expect(screen.getByText("Opened from Daikon")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Daikon" })).toHaveAttribute(
      "href",
      target.url,
    );
  });

  it("names the protocol it goes back with", () => {
    render(<ReturnToBar target={target} protocolId="p1" protocolCode="PRT-00123" />);
    const link = screen.getByRole("link", { name: "Back to Daikon with PRT-00123" });
    expect(link.getAttribute("href")).toContain("protocol_id=p1");
  });

  it("says 'this protocol' when the protocol has no code", () => {
    render(<ReturnToBar target={target} protocolId="p1" protocolCode={null} />);
    expect(screen.getByRole("link", { name: "Back to Daikon with this protocol" })).toBeVisible();
  });
});

describe("ReturnToBarFromUrl", () => {
  const config = { returnOrigins: [{ label: "Daikon", origin: "https://d.org" }] } as AppConfig;
  const renderFromUrl = (returnTo: string) => {
    state.params = new URLSearchParams({ return_to: returnTo });
    return render(
      <AppConfigProvider config={config}>
        <ReturnToBarFromUrl protocolId="p1" protocolCode="PRT-00123" />
      </AppConfigProvider>,
    );
  };

  beforeEach(() => {
    state.params = new URLSearchParams();
  });

  it("shows the way back for a trusted return address", async () => {
    renderFromUrl(target.url);
    expect(
      await screen.findByRole("link", { name: "Back to Daikon with PRT-00123" }),
    ).toBeVisible();
  });

  it("shows nothing for an address on another origin", () => {
    const { container } = renderFromUrl("https://d.org.evil.com/x");
    expect(container).toBeEmptyDOMElement();
  });
});
