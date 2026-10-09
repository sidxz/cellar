import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async () => ({})),
}));
vi.mock("@/shared/lib/toast", () => ({ showError: vi.fn(), showSuccess: vi.fn() }));

import {
  useCreateProtocolCategory,
  useDeleteProtocolCategory,
  useSeedDefaultProtocolCategories,
} from "./use-protocol-categories";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { wrapper, invalidateSpy };
}

type Mutation = { mutate: (arg: never) => void; isSuccess: boolean };

describe("protocol category mutations", () => {
  // Creating (with "start like"), adding the defaults and deleting all change the forms list.
  it.each<[string, () => Mutation, unknown]>([
    ["create", useCreateProtocolCategory, { label: "Biofilm inhibition" }],
    ["add defaults", useSeedDefaultProtocolCategories, undefined],
    ["delete", useDeleteProtocolCategory, "c1"],
  ])("%s refreshes the categories and the forms", async (_, useHook, arg) => {
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(useHook, { wrapper });
    (result.current.mutate as (a: unknown) => void)(arg);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["protocol-categories"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["protocol-forms"] });
  });
});
