import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { PlateGroupDetails } from "./plate-group-details";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

const node: PlateGroupNode = {
  id: "g1",
  name: "Vendor Library A",
  group_type: "vendor",
  description: "Legacy vendor set",
  parent_group_id: null,
  owner_org_id: "org1",
  plate_count: 1,
  created_by: "u1",
  version: 1,
  children: [],
};

function setup(props: Partial<Parameters<typeof PlateGroupDetails>[0]> = {}) {
  mocked.mockImplementation((opts: { url: string }) => {
    if (opts.url.includes("/orgs")) {
      return Promise.resolve([{ id: "org1", slug: "acme", name: "Acme Labs" }]);
    }
    return Promise.resolve([
      { id: "p1", barcode: "000123", plate_label: "Plate 123", group_id: "g1" },
    ]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PlateGroupDetails node={node} {...props} />, { wrapper });
}

describe("PlateGroupDetails", () => {
  it("shows metadata, org name, and plates", async () => {
    setup();
    expect(screen.getByText("Vendor Library A")).toBeInTheDocument();
    expect(screen.getByText("vendor")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Acme Labs")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("000123")).toBeInTheDocument());
  });

  it("fires onRemovePlates with the plate id", async () => {
    const onRemovePlates = vi.fn();
    setup({ onRemovePlates });
    const btn = await screen.findByRole("button", { name: /remove 000123/i });
    fireEvent.click(btn);
    expect(onRemovePlates).toHaveBeenCalledWith(["p1"]);
  });

  it("fires action callbacks", () => {
    const onEdit = vi.fn();
    setup({ onEdit });
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalled();
  });
});
