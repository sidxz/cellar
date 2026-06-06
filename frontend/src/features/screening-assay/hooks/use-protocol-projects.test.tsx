import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useAssignProtocolToProject } from "./use-protocol-projects";

const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;
const mockShowError = showError as ReturnType<typeof vi.fn>;
const mockShowSuccess = showSuccess as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { wrapper, invalidateSpy };
}

describe("useAssignProtocolToProject", () => {
  beforeEach(() => {
    mockCustomInstance.mockReset();
    mockShowError.mockReset();
    mockShowSuccess.mockReset();
  });

  it("POSTs the protocol/project link and invalidates the protocols cache on success", async () => {
    mockCustomInstance.mockResolvedValue({ id: "proto-1" });
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useAssignProtocolToProject(), { wrapper });

    result.current.mutate({ protocolId: "proto-1", projectId: "proj-9" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCustomInstance).toHaveBeenCalledWith({
      url: "/api/v1/protocols/proto-1/projects/proj-9",
      method: "POST",
    });
    // Root key refetches every project-scoped protocol list.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["protocols"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["protocols", "proto-1"] });
    // Create flow already toasted success — this assignment stays silent.
    expect(mockShowSuccess).not.toHaveBeenCalled();
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it("surfaces a recovery-hint error toast on failure without invalidating", async () => {
    mockCustomInstance.mockRejectedValue(new Error("boom"));
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useAssignProtocolToProject(), { wrapper });

    result.current.mutate({ protocolId: "proto-1", projectId: "proj-9" });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(mockShowError).toHaveBeenCalledWith(
      "Protocol created but could not be added to the project — add it manually from the project page.",
    );
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
