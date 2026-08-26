import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateGroupDetailResponse } from "@/shared/lib/api/model";
import { useBreadcrumbTrailValue } from "@/shared/lib/stores/breadcrumb-store";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlateGroupPage } from "./plate-group-page";

// DetailShell only PUBLISHES the breadcrumb trail to a global store — the
// actual <nav> lives in the app-chrome layout, not under this component.
// This probe renders alongside the page so the trail is observable here.
function BreadcrumbProbe() {
  const trail = useBreadcrumbTrailValue();
  return (
    <div data-testid="breadcrumb-probe">
      {(trail ?? []).map((c) => (
        <a key={c.label} href={c.href}>
          {c.label}
        </a>
      ))}
    </div>
  );
}

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/inventory/plate-groups/g1",
}));

const mocked = vi.mocked(customInstance);

const baseDetail: PlateGroupDetailResponse = {
  group: {
    id: "g1",
    workspace_id: "ws1",
    owner_org_id: "org1",
    name: "Vendor Library A",
    parent_group_id: "mid1",
    group_type: "vendor",
    description: "Legacy vendor set",
    state: "Solubilized",
    storage_location_id: "loc-1",
    initial_volume_ul: 55,
    initial_concentration_mm: 10,
    compound_count: 17606,
    scientist: "Jane Doe",
    created_at: "2026-08-25T10:00:00Z",
    created_by: "u1",
    version: 1,
  },
  plate_count: 2,
  subtree_plate_count: 5,
  plate_format: "96",
  ancestors: [
    { id: "root1", name: "Root Library", group_type: "vendor", plate_count: 10 },
    { id: "mid1", name: "Mid Group", plate_count: 6 },
  ],
  children: [{ id: "child1", name: "Child Group", group_type: "screening", plate_count: 3 }],
};

function setup(detail: PlateGroupDetailResponse = baseDetail) {
  mocked.mockImplementation((opts: { url: string; params?: Record<string, unknown> }) => {
    if (opts.url === "/api/v1/plate-groups/g1") return Promise.resolve(detail);
    if (opts.url === "/api/v1/plates") {
      return Promise.resolve([
        { id: "p1", barcode: "000123", plate_label: "Plate 123", status: "stored", group_id: "g1" },
        { id: "p2", barcode: "000456", plate_label: "Plate 456", status: "in_use", group_id: "g1" },
      ]);
    }
    if (opts.url === "/api/v1/comments") return Promise.resolve([]);
    if (opts.url === "/api/v1/orgs") {
      return Promise.resolve([{ id: "org1", slug: "acme", name: "Acme Labs" }]);
    }
    if (opts.url === "/api/v1/storage-locations") {
      return Promise.resolve([{ id: "loc-1", name: "Room 1148 / Freezer 4" }]);
    }
    if (opts.url === "/api/v1/plate-loans") return Promise.resolve([]);
    if (opts.url === "/api/v1/user/me") {
      return Promise.resolve({
        user_id: "u1",
        email: "",
        name: "",
        org_id: "org1",
        is_admin: false,
        workspace_role: "editor",
      });
    }
    return Promise.resolve([]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <>
      <PlateGroupPage groupId="g1" />
      <BreadcrumbProbe />
    </>,
    { wrapper },
  );
}

describe("PlateGroupPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the title, breadcrumb ancestors, details, children, plates, and activity", async () => {
    setup();

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Vendor Library A" })).toBeInTheDocument(),
    );

    // Breadcrumb ancestor names (root-first), published via the global store.
    await waitFor(() => {
      const crumbs = within(screen.getByTestId("breadcrumb-probe"));
      expect(crumbs.getByRole("link", { name: "Root Library" })).toHaveAttribute(
        "href",
        "/inventory/plate-groups/root1",
      );
      expect(crumbs.getByRole("link", { name: "Mid Group" })).toHaveAttribute(
        "href",
        "/inventory/plate-groups/mid1",
      );
    });

    // Details card rows.
    expect(await screen.findByText("96-well")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("55 µL · 10 mM")).toBeInTheDocument();
    expect(screen.getByText("17,606")).toBeInTheDocument();
    expect(screen.getByText("2 direct · 5 in subtree")).toBeInTheDocument();

    // Child group link.
    const childLink = screen.getByRole("link", { name: /Child Group/ });
    expect(childLink).toHaveAttribute("href", "/inventory/plate-groups/child1");

    // Plates.
    expect(screen.getByText("000123")).toBeInTheDocument();
    expect(screen.getByText("000456")).toBeInTheDocument();

    // Activity card.
    expect(
      screen.getByText("No activity yet — return notes and comments on this group appear here."),
    ).toBeInTheDocument();

    // Action buttons.
    const actions = screen.getByRole("button", { name: "Add child" }).closest("div");
    expect(actions).not.toBeNull();
    if (actions) {
      expect(within(actions).getByRole("button", { name: "Request loan" })).toBeInTheDocument();
      expect(within(actions).getByRole("button", { name: "Add plates" })).toBeInTheDocument();
      expect(within(actions).getByRole("button", { name: "Edit" })).toBeInTheDocument();
      expect(within(actions).getByRole("button", { name: "Move" })).toBeInTheDocument();
      expect(within(actions).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    }
  });

  it("hides Request loan when the subtree has no plates", async () => {
    setup({ ...baseDetail, subtree_plate_count: 0 });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Vendor Library A" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
  });
});
