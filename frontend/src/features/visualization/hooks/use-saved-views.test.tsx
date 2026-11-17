import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useSavedView } from "./use-saved-views";

describe("useSavedView", () => {
  it("opens a view as saved now each time, never a version cached from an earlier opening", async () => {
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    vi.mocked(customInstance).mockResolvedValueOnce({ id: "v1", version: 1 });
    const first = renderHook(() => useSavedView("v1"), { wrapper });
    await waitFor(() => expect(first.result.current.data).toEqual({ id: "v1", version: 1 }));
    first.unmount();
    // The chemist leaves; someone else saves version 2; the chemist opens the view again.
    await new Promise((r) => setTimeout(r, 10));
    vi.mocked(customInstance).mockResolvedValueOnce({ id: "v1", version: 2 });

    const seen: unknown[] = [];
    const again = renderHook(
      () => {
        const query = useSavedView("v1");
        seen.push(query.data);
        return query;
      },
      { wrapper },
    );
    await waitFor(() => expect(again.result.current.data).toEqual({ id: "v1", version: 2 }));
    expect(seen).not.toContainEqual({ id: "v1", version: 1 });
  });
});
