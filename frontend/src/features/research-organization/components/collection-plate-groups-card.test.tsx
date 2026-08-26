import { customInstance } from "@/shared/lib/api/custom-instance";
import type { CollectionPlateGroupResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CollectionPlateGroupsCard } from "./collection-plate-groups-card";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// Radix Select (inside RequestLoanDialog) needs these in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const mocked = vi.mocked(customInstance);

const rows: CollectionPlateGroupResponse[] = [
  {
    group_id: "g1",
    name: "SAC1",
    group_type: "vendor",
    owner_org_id: "org1",
    path: "SAC1",
    plate_count: 0,
    subtree_plate_count: 42,
    on_loan_count: 3,
    overdue_count: 1,
  },
  {
    group_id: "g2",
    name: "Set 014",
    group_type: "hit_collection",
    owner_org_id: "org1",
    path: "SAC1 › Set 014",
    plate_count: 0,
    subtree_plate_count: 0,
    on_loan_count: 0,
    overdue_count: 0,
  },
];

function setup(groups: CollectionPlateGroupResponse[], role = "editor") {
  mocked.mockImplementation((opts: { url: string }) => {
    if (opts.url === "/api/v1/collections/c1/plate-groups") return Promise.resolve(groups);
    if (opts.url === "/api/v1/user/me") {
      return Promise.resolve({ user_id: "u1", org_id: "org1", workspace_role: role });
    }
    if (opts.url === "/api/v1/plate-groups/tree") {
      return Promise.resolve({
        roots: [{ id: "g1", name: "SAC1", plate_count: 42, owner_org_id: "org1", children: [] }],
      });
    }
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<CollectionPlateGroupsCard collectionId="c1" />, { wrapper });
}

describe("CollectionPlateGroupsCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists one row per group with path link, type, counts and loan colours", async () => {
    setup(rows);
    expect(await screen.findByRole("link", { name: "SAC1" })).toHaveAttribute(
      "href",
      "/inventory/plate-groups/g1",
    );
    expect(screen.getByRole("link", { name: "SAC1 › Set 014" })).toHaveAttribute(
      "href",
      "/inventory/plate-groups/g2",
    );
    expect(screen.getByText("vendor")).toBeInTheDocument();
    expect(screen.getByText("42 plates")).toBeInTheDocument();
    expect(screen.getByText("3 on loan")).toHaveClass("text-warning");
    expect(screen.getByText("1 overdue")).toHaveClass("text-destructive");
    // Zero counts stay silent.
    expect(screen.getByText("0 plates")).toBeInTheDocument();
    expect(screen.queryByText("0 on loan")).not.toBeInTheDocument();
    expect(screen.queryByText("0 overdue")).not.toBeInTheDocument();
    // Request loan only where the subtree has plates.
    expect(screen.getAllByRole("button", { name: "Request loan" })).toHaveLength(1);
  });

  it("shows the empty copy when nothing is linked", async () => {
    setup([]);
    expect(
      await screen.findByText(
        "No plate groups realize this collection yet — link one from a group's Edit dialog.",
      ),
    ).toBeInTheDocument();
  });

  it("hides Request loan for viewers", async () => {
    setup(rows, "viewer");
    await screen.findByRole("link", { name: "SAC1" });
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });

  it("Request loan opens the loan dialog in group mode with the group preselected", async () => {
    setup(rows);
    fireEvent.click(await screen.findByRole("button", { name: "Request loan" }));
    expect(await screen.findByRole("dialog", { name: "Request loan" })).toBeInTheDocument();
    // Group mode: the owner org's tree is fetched and the row's group is preselected.
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ url: "/api/v1/plate-groups/tree", params: { org_id: "org1" } }),
      ),
    );
    expect(await screen.findByText("SAC1 (42)")).toBeInTheDocument();
  });
});
