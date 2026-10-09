import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showError: vi.fn(), showSuccess: vi.fn() }));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useSeedDefaultProtocolForms } from "./use-protocol-forms";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("useSeedDefaultProtocolForms", () => {
  beforeEach(() => vi.mocked(showSuccess).mockReset());

  // The endpoint returns only the forms it created.
  it.each([
    [[{ id: "f1" }, { id: "f2" }], "Default forms added (2)"],
    [[], "No new default forms to add"],
  ])("reports %j as %s", async (created, message) => {
    vi.mocked(customInstance).mockResolvedValue(created);
    const { result } = renderHook(() => useSeedDefaultProtocolForms(), { wrapper });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(customInstance).toHaveBeenCalledWith({
      url: "/api/v1/protocol-forms/defaults",
      method: "POST",
    });
    expect(showSuccess).toHaveBeenCalledWith(message);
  });
});
