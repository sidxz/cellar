import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const customInstance = vi.fn(async (_args: unknown) => ({ id: "l1", items: [] }));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import type { PlateLoan } from "../hooks/use-plate-loans";
import { RequestReturnDialog } from "./request-return-dialog";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const loan = {
  id: "l1",
  status: "open",
  owner_org_id: "org-A",
  borrower_org_id: "org-B",
  requested_by: "u1",
  due_date: null,
  notes: null,
  items: [
    {
      id: "i1",
      plate_id: "p1",
      barcode: "BC-1",
      plate_label: "Plate 1",
      status: "checked_out",
      status_changed_at: "2026-08-13T00:00:00Z",
      group_id: "g1",
      group_name: "Vendor A",
    },
    {
      id: "i2",
      plate_id: "p2",
      barcode: "BC-2",
      plate_label: "Plate 2",
      status: "checked_out",
      status_changed_at: "2026-08-13T00:00:00Z",
      group_id: "g2",
      group_name: "Screen B",
    },
    {
      id: "i3",
      plate_id: "p3",
      barcode: "BC-3",
      plate_label: "Plate 3",
      status: "checked_out",
      status_changed_at: "2026-08-13T00:00:00Z",
    },
  ],
  plates: {},
  created_at: "2026-08-13T00:00:00Z",
} as unknown as PlateLoan;

describe("RequestReturnDialog", () => {
  beforeEach(() => {
    customInstance.mockClear();
  });

  it("requires one non-blank note per group and submits comments + item_ids", async () => {
    render(
      <RequestReturnDialog open onOpenChange={() => {}} loan={loan} itemIds={["i1", "i2", "i3"]} />,
      { wrapper },
    );

    const groupANote = screen.getByLabelText(/vendor a \(bc-1\)/i);
    const groupBNote = screen.getByLabelText(/screen b \(bc-2\)/i);
    expect(groupANote).toBeInTheDocument();
    expect(groupBNote).toBeInTheDocument();
    // Ungrouped item p3 gets no required textarea in the main section.
    expect(screen.queryByLabelText(/bc-3/i)).not.toBeInTheDocument();

    const submit = screen.getByRole("button", { name: /request return/i });
    expect(submit).toBeDisabled();

    fireEvent.change(groupANote, { target: { value: "a" } });
    expect(submit).toBeDisabled();
    fireEvent.change(groupBNote, { target: { value: "b" } });
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);

    await waitFor(() =>
      expect(customInstance).toHaveBeenCalledWith(
        expect.objectContaining({
          url: expect.stringMatching(/items:request-return$/),
          method: "POST",
          data: {
            item_ids: ["i1", "i2", "i3"],
            comments: [
              { group_id: "g1", body: "a" },
              { group_id: "g2", body: "b" },
            ],
            plate_comments: [],
          },
        }),
      ),
    );
  });

  it("an ungrouped-only selection has no group textareas and submits immediately", () => {
    render(<RequestReturnDialog open onOpenChange={() => {}} loan={loan} itemIds={["i3"]} />, {
      wrapper,
    });

    expect(screen.queryByLabelText(/vendor a/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/screen b/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /request return/i })).not.toBeDisabled();
  });
});
