import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSimilarProtocols } from "./use-similar-protocols";

const post = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (cfg: unknown) => post(cfg),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useSimilarProtocols", () => {
  beforeEach(() => post.mockReset().mockResolvedValue([]));

  it("does not query when the name is too short", async () => {
    renderHook(() => useSimilarProtocols({ name: "a" }), { wrapper });
    await new Promise((r) => setTimeout(r, 350));
    expect(post).not.toHaveBeenCalled();
  });

  it("POSTs the draft once the name is long enough", async () => {
    renderHook(() => useSimilarProtocols({ name: "RNAP core IC50", readout_names: ["IC50"] }), {
      wrapper,
    });
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ url: "/api/v1/protocols/similar", method: "POST" }),
    );
  });
});
