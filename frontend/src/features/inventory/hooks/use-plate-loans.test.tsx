import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  type PlateLoan,
  buildCustodyMap,
  useLoan,
  useLoanItemsAction,
  useLoans,
  useRequestLoan,
} from "./use-plate-loans";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useLoans", () => {
  beforeEach(() => vi.clearAllMocks());

  it("omits all params when no filters given", async () => {
    mocked.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useLoans(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-loans",
        method: "GET",
        params: {},
      }),
    );
  });

  it("passes set filters, including booleans only when true", async () => {
    mocked.mockResolvedValueOnce([]);
    const { result } = renderHook(
      () =>
        useLoans({
          status: "open",
          mine: true,
          owner_org_id: "org-1",
          borrower_org_id: "org-2",
          plate_id: "plate-1",
          overdue: true,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-loans",
        method: "GET",
        params: {
          status: "open",
          mine: true,
          owner_org_id: "org-1",
          borrower_org_id: "org-2",
          plate_id: "plate-1",
          overdue: true,
        },
      }),
    );
  });

  it("drops mine/overdue from params when false", async () => {
    mocked.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useLoans({ mine: false, overdue: false }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(expect.objectContaining({ params: {} }));
  });

  it("respects enabled=false", () => {
    renderHook(() => useLoans(undefined, { enabled: false }), { wrapper });
    expect(mocked).not.toHaveBeenCalled();
  });
});

describe("useLoan", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches a single loan by id", async () => {
    mocked.mockResolvedValueOnce({ id: "l1" });
    const { result } = renderHook(() => useLoan("l1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ url: "/api/v1/plate-loans/l1", method: "GET" }),
    );
  });

  it("respects enabled=false", () => {
    renderHook(() => useLoan("l1", { enabled: false }), { wrapper });
    expect(mocked).not.toHaveBeenCalled();
  });
});

describe("useRequestLoan", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs the request body", async () => {
    mocked.mockResolvedValueOnce({ id: "l1" });
    const { result } = renderHook(() => useRequestLoan(), { wrapper });
    result.current.mutate({ plate_ids: ["p1"], notes: "for testing" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-loans",
        method: "POST",
        data: { plate_ids: ["p1"], notes: "for testing" },
      }),
    );
  });
});

describe("useLoanItemsAction", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts items:approve with item_ids: null when itemIds omitted", async () => {
    mocked.mockResolvedValueOnce({ id: "l1" });
    const { result } = renderHook(() => useLoanItemsAction(), { wrapper });
    result.current.mutate({ loanId: "l1", verb: "approve" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-loans/l1/items:approve",
        method: "POST",
        data: { item_ids: null },
      }),
    );
  });

  it("posts items:confirm-out with the given itemIds", async () => {
    mocked.mockResolvedValueOnce({ id: "l1" });
    const { result } = renderHook(() => useLoanItemsAction(), { wrapper });
    result.current.mutate({ loanId: "l1", verb: "confirm-out", itemIds: ["i1", "i2"] });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-loans/l1/items:confirm-out",
        method: "POST",
        data: { item_ids: ["i1", "i2"] },
      }),
    );
  });
});

describe("buildCustodyMap", () => {
  const baseLoan: PlateLoan = {
    id: "l1",
    workspace_id: "w1",
    owner_org_id: "o1",
    borrower_org_id: "o2",
    requested_by: "u1",
    status: "open",
    created_at: "2026-01-01T00:00:00Z",
    version: 1,
    items: [],
  };

  it("maps a plate to its active item on an open loan", () => {
    const loans: PlateLoan[] = [
      {
        ...baseLoan,
        items: [
          {
            id: "i1",
            plate_id: "p1",
            barcode: "B1",
            plate_label: "P1",
            status: "checked_out",
            status_changed_at: "2026-01-01T00:00:00Z",
          },
        ],
      },
    ];
    const map = buildCustodyMap(loans);
    expect(map.get("p1")?.item.id).toBe("i1");
    expect(map.get("p1")?.loan.id).toBe("l1");
  });

  it("ignores a returned item", () => {
    const loans: PlateLoan[] = [
      {
        ...baseLoan,
        items: [
          {
            id: "i1",
            plate_id: "p1",
            barcode: "B1",
            plate_label: "P1",
            status: "returned",
            status_changed_at: "2026-01-01T00:00:00Z",
          },
        ],
      },
    ];
    expect(buildCustodyMap(loans).has("p1")).toBe(false);
  });

  it("ignores items on a closed loan even if item status looks active", () => {
    const loans: PlateLoan[] = [
      {
        ...baseLoan,
        status: "closed",
        items: [
          {
            id: "i1",
            plate_id: "p1",
            barcode: "B1",
            plate_label: "P1",
            status: "requested",
            status_changed_at: "2026-01-01T00:00:00Z",
          },
        ],
      },
    ];
    expect(buildCustodyMap(loans).has("p1")).toBe(false);
  });
});
