import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async (opts: { method: string }) => (opts.method === "GET" ? [] : {})),
}));
vi.mock("@/shared/lib/toast", () => ({ showError: vi.fn(), showSuccess: vi.fn() }));

import {
  useCreateProtocolCategory,
  useDeleteProtocolCategory,
  useProtocolCategories,
  useSeedDefaultProtocolCategories,
} from "./use-protocol-categories";
import { useProtocolForms } from "./use-protocol-forms";
import { useWorkspaceSetup } from "./use-workspace-setup";

const mocked = vi.mocked(customInstance);
const LISTS = ["/api/v1/protocol-categories", "/api/v1/protocol-forms", "/api/v1/workspace-setup"];
const fetches = (url: string) =>
  mocked.mock.calls.filter(([o]) => o.url === url && o.method === "GET").length;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

type Mutation = { mutate: (arg: never) => void; isSuccess: boolean };

describe("protocol category mutations", () => {
  // Creating (with "start like"), adding the defaults and deleting all change the forms list.
  it.each<[string, () => Mutation, unknown]>([
    ["create", useCreateProtocolCategory, { label: "Biofilm inhibition" }],
    ["add defaults", useSeedDefaultProtocolCategories, undefined],
    ["delete", useDeleteProtocolCategory, "c1"],
  ])(
    "%s refetches the categories, the forms and the setup checklist on screen",
    async (_, useHook, arg) => {
      mocked.mockClear();
      const { result } = renderHook(
        () => ({
          mutation: useHook(),
          lists: [useProtocolCategories(), useProtocolForms(), useWorkspaceSetup(true)],
        }),
        { wrapper },
      );
      await waitFor(() => expect(result.current.lists.every((q) => q.isSuccess)).toBe(true));
      expect(LISTS.map(fetches)).toEqual([1, 1, 1]);

      (result.current.mutation.mutate as (a: unknown) => void)(arg);
      await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));
      await waitFor(() => expect(LISTS.map(fetches)).toEqual([2, 2, 2]));
    },
  );
});
