import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useRGroupDecomposition } from "./use-rgroup-decomposition";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useRGroupDecomposition", () => {
  it("posts the molecule set + core and returns the decomposition", async () => {
    const decomposeFn = vi.fn().mockResolvedValue({
      core_smiles: "c1ccccc1",
      rgroup_labels: ["R1"],
      assignments: [{ molecule_id: "m1", rgroups: { R1: "F[*:1]" } }],
      unmatched_ids: [],
    });
    const { result } = renderHook(() => useRGroupDecomposition({ decomposeFn }), {
      wrapper: makeWrapper(),
    });
    let res: unknown;
    await act(async () => {
      res = await result.current.mutateAsync({
        moleculeIds: ["m1"],
        coreSmiles: "c1ccccc1",
      });
    });
    expect(decomposeFn).toHaveBeenCalledWith({
      molecule_ids: ["m1"],
      core_smiles: "c1ccccc1",
    });
    expect((res as { rgroup_labels: string[] }).rgroup_labels).toEqual(["R1"]);
  });

  it("passes collectionId instead of moleculeIds when provided", async () => {
    const decomposeFn = vi.fn().mockResolvedValue({
      core_smiles: "c1ccccc1",
      rgroup_labels: [],
      assignments: [],
      unmatched_ids: [],
    });
    const { result } = renderHook(() => useRGroupDecomposition({ decomposeFn }), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        collectionId: "col-42",
        coreSmiles: "c1ccccc1",
      });
    });
    expect(decomposeFn).toHaveBeenCalledWith({
      collection_id: "col-42",
      core_smiles: "c1ccccc1",
    });
  });
});
