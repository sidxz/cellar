import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PlateGroupDialog } from "./plate-group-dialog";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test (verbatim from org-plate-policy-dialog.test.tsx).
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

function setup(props: Partial<Parameters<typeof PlateGroupDialog>[0]> = {}) {
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url.includes("/vocabularies")) return Promise.resolve([]);
    return Promise.resolve({ id: "g-new", name: "New Group" });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <PlateGroupDialog
      open
      onOpenChange={() => {}}
      orgId="org1"
      parentGroupId={null}
      group={null}
      {...props}
    />,
    { wrapper },
  );
}

describe("PlateGroupDialog", () => {
  it("disables Save until a name is entered, then POSTs the create body", async () => {
    setup();
    const save = screen.getByRole("button", { name: /create/i });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Vendor Set 1" } });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-groups",
          method: "POST",
          data: expect.objectContaining({
            name: "Vendor Set 1",
            owner_org_id: "org1",
            parent_group_id: null,
          }),
        }),
      ),
    );
  });

  it("edit mode PATCHes only the changed fields", async () => {
    setup({
      group: {
        id: "g1",
        name: "Old Name",
        group_type: "vendor",
        description: null,
        parent_group_id: null,
        owner_org_id: "org1",
        plate_count: 0,
        created_by: "u1",
        version: 1,
        children: [],
      },
    });
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "New Name" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-groups/g1",
          method: "PATCH",
          data: expect.objectContaining({ name: "New Name" }),
        }),
      ),
    );
  });
});
