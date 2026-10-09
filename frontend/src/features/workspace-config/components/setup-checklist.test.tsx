import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const role = vi.hoisted(() => ({ admin: true, workspaceId: "ws-a" }));
vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: () => role.admin,
  useAuthz: () => ({ user: { workspaceId: role.workspaceId } }),
}));

const setup = vi.hoisted(() => ({
  missing_default_categories: ["Biofilm", "MIC"],
  missing_default_forms: 3,
  bioportal_key: false,
  home_organisms: 0,
  targets: 0,
}));
const mutate = vi.hoisted(() => vi.fn());
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async () => setup),
}));
vi.mock("../hooks/use-protocol-categories", () => ({
  useSeedDefaultProtocolCategories: () => ({ mutate, isPending: false }),
}));

import { SetupChecklist } from "./setup-checklist";

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SetupChecklist />
    </QueryClientProvider>,
  );
}

describe("SetupChecklist", () => {
  beforeEach(() => {
    role.admin = true;
    role.workspaceId = "ws-a";
    window.localStorage.clear();
    Object.assign(setup, {
      missing_default_categories: ["Biofilm", "MIC"],
      missing_default_forms: 3,
      bioportal_key: false,
      home_organisms: 0,
      targets: 0,
    });
  });

  it("shows an admin what is missing, with links to the admin pages", async () => {
    renderIt();
    expect(await screen.findByText(/Finish setting up protocols/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /api keys/i })).toHaveAttribute(
      "href",
      "/admin/api-keys",
    );
    expect(screen.getByRole("link", { name: /home organism/i })).toHaveAttribute(
      "href",
      "/admin/settings#home-organisms",
    );
    expect(screen.getByRole("link", { name: /targets/i })).toHaveAttribute(
      "href",
      "/admin/targets",
    );
    expect(screen.getByRole("link", { name: /forms/i })).toHaveAttribute(
      "href",
      "/admin/protocol-forms",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add 2 new shipped categories" }));
    expect(mutate).toHaveBeenCalled();
  });

  it("is hidden from a viewer", async () => {
    role.admin = false;
    renderIt();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Finish setting up protocols/i)).not.toBeInTheDocument();
  });

  it("is hidden once everything is done", async () => {
    Object.assign(setup, {
      missing_default_categories: [],
      missing_default_forms: 0,
      bioportal_key: true,
      home_organisms: 1,
      targets: 4,
    });
    renderIt();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Finish setting up protocols/i)).not.toBeInTheDocument();
  });

  it("Dismiss hides it for this viewer and stays hidden on the next visit", async () => {
    const first = renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/Finish setting up protocols/i)).not.toBeInTheDocument();
    first.unmount();
    renderIt();
    await new Promise((r) => setTimeout(r, 20));
    await waitFor(() =>
      expect(screen.queryByText(/Finish setting up protocols/i)).not.toBeInTheDocument(),
    );
  });

  async function dismissAndRevisit() {
    const first = renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    first.unmount();
    return renderIt();
  }

  it("a dismissal in one workspace does not hide it in another", async () => {
    await dismissAndRevisit();
    cleanup();
    role.workspaceId = "ws-b";
    renderIt();
    expect(await screen.findByText(/Finish setting up protocols/i)).toBeInTheDocument();
  });

  it("stays dismissed when something gets fixed, comes back when something new is missing", async () => {
    await dismissAndRevisit();
    cleanup();
    Object.assign(setup, { targets: 3 });
    renderIt();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Finish setting up protocols/i)).not.toBeInTheDocument();
    cleanup();
    // A later release ships a category this workspace does not have yet.
    Object.assign(setup, { missing_default_categories: ["Biofilm", "MIC", "Hepatotoxicity"] });
    renderIt();
    expect(await screen.findByText(/Finish setting up protocols/i)).toBeInTheDocument();
  });
});
