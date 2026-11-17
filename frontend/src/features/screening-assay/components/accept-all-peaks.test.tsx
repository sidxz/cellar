import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MeltingAnalysis } from "../types";
import { AcceptAllPeaks } from "./accept-all-peaks";

const customInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));

const analysis = (statuses: string[], edit_refusal: string | null = null) =>
  ({
    edit_refusal,
    windows: [{ channel_key: "ratio", positions: statuses.map((_, i) => ({ step_id: `s${i}` })) }],
    steps: statuses.map((status, i) => ({ id: `s${i}`, status, version: 2 })),
  }) as unknown as MeltingAnalysis;

function show(a: MeltingAnalysis) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<AcceptAllPeaks runId="r1" analysis={a} channel="ratio" />, { wrapper });
}

describe("AcceptAllPeaks", () => {
  beforeEach(() => customInstance.mockReset());

  it("shows the count beside the button and sends every unreviewed peak in one request", async () => {
    customInstance.mockResolvedValue({ steps: [], skipped: 0, compute_warning: null });
    show(analysis(["unreviewed", "accepted", "unreviewed"]));
    expect(screen.getByText("2 peaks")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Accept all" }));
    await waitFor(() => expect(customInstance).toHaveBeenCalledTimes(1));
    expect(customInstance).toHaveBeenCalledWith({
      url: "/api/v1/runs/r1/melting-steps/accept",
      method: "POST",
      data: {
        steps: [
          { id: "s0", expected_version: 2 },
          { id: "s2", expected_version: 2 },
        ],
      },
    });
  });

  it("says 1 peak for one", () => {
    show(analysis(["unreviewed"]));
    expect(screen.getByText("1 peak")).toBeInTheDocument();
  });

  it("shows nothing when every peak is reviewed", () => {
    const { container } = show(analysis(["accepted", "accepted"]));
    expect(container).toBeEmptyDOMElement();
  });

  it("is disabled, with the reason as its title, on a run that refuses peak edits", () => {
    show(analysis(["unreviewed"], "Peaks cannot be changed on an approved run"));
    const button = screen.getByRole("button", { name: "Accept all" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Peaks cannot be changed on an approved run");
  });

  it("shows the server's reason when the request fails", async () => {
    customInstance.mockRejectedValueOnce(new Error("API error: 409 — A peak changed. Reload."));
    show(analysis(["unreviewed"]));
    fireEvent.click(screen.getByRole("button", { name: "Accept all" }));
    expect(await screen.findByText("A peak changed. Reload.")).toBeInTheDocument();
  });
});
