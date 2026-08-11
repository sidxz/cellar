import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const policyA = {
  org_id: "org-a",
  require_approval: true,
  confirmation: "admin_confirm",
  default_due_days: 14,
  plates_private: true,
  version: 1,
};

// org-a's policy resolves; org-b's stays pending forever to freeze the
// loading window the stale-save bug lived in.
const customInstance = vi.fn(async (args: { url: string; method: string }) => {
  if (args.url === "/api/v1/orgs") {
    return [
      { id: "org-a", slug: "org-a", name: "Org A" },
      { id: "org-b", slug: "org-b", name: "Org B" },
    ];
  }
  if (args.url === "/api/v1/org-plate-policies/org-a") return policyA;
  if (args.url === "/api/v1/org-plate-policies/org-b") return new Promise(() => {});
  throw new Error(`unexpected ${args.method} ${args.url}`);
});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args as never),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { OrgPlatePolicyDialog } from "./org-plate-policy-dialog";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test.
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

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<OrgPlatePolicyDialog open onOpenChange={vi.fn()} />, { wrapper });
}

/** Open the org picker (first combobox) and choose an org by name. */
async function pickOrg(name: string) {
  fireEvent.click(screen.getAllByRole("combobox")[0]);
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("OrgPlatePolicyDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("disables Save until an org is picked", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("disables Save while the selected org's policy is still loading", async () => {
    renderDialog();
    await pickOrg("Org B"); // policy fetch never resolves
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("prefills from the loaded policy, then clears it when switching to an org still loading", async () => {
    renderDialog();
    await pickOrg("Org A");

    // Org A's policy prefills the form.
    const approvalSwitch = await screen.findByRole("switch", {
      name: /require approval/i,
    });
    expect(approvalSwitch).toBeChecked();
    expect(screen.getByLabelText(/default due days/i)).toHaveValue(14);
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    // Switch to Org B (policy pending): A's values must not linger, and Save
    // must not be able to write them onto B.
    await pickOrg("Org B");
    expect(screen.queryByRole("switch", { name: /require approval/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(customInstance).not.toHaveBeenCalledWith(expect.objectContaining({ method: "PUT" }));
  });
});
