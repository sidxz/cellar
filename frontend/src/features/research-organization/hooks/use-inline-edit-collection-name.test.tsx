import { describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useInlineEditCollectionName } from "./use-inline-edit-collection-name";

const mockMutate = vi.fn();
vi.mock("./use-collections", () => ({
  useUpdateCollection: (_id: string) => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useInlineEditCollectionName", () => {
  it("commit() fires the mutation with the new name", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("Updated"));
    act(() => result.current.commit());
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate.mock.calls[0][0]).toEqual({ name: "Updated" });
  });

  it("commit() with unchanged draft is a no-op (skip the round-trip)", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.commit());
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("commit() with whitespace-only draft is rejected (no-op)", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("   "));
    act(() => result.current.commit());
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("cancel() resets the draft and exits edit mode", () => {
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("Changed"));
    act(() => result.current.cancel());
    expect(result.current.isEditing).toBe(false);
    expect(result.current.draft).toBe("Original");
  });

  it("syncs draft from currentName updates when not editing", () => {
    const { result, rerender } = renderHook(
      ({ name }) => useInlineEditCollectionName("c1", name),
      { wrapper, initialProps: { name: "Original" } },
    );
    rerender({ name: "Server-updated" });
    expect(result.current.draft).toBe("Server-updated");
  });

  it("does not overwrite draft mid-edit when currentName updates", () => {
    const { result, rerender } = renderHook(
      ({ name }) => useInlineEditCollectionName("c1", name),
      { wrapper, initialProps: { name: "Original" } },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("In Progress"));
    rerender({ name: "Server-updated" });
    expect(result.current.draft).toBe("In Progress");
  });
});
