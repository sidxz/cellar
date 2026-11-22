import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Molecule } from "../../types";

const h = vi.hoisted(() => ({
  me: { user_id: "u-reg", is_admin: false, org_id: "org-tamu", workspace_role: "editor" },
  audit: [] as unknown[],
  put: vi.fn().mockResolvedValue({}),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: h.push }) }));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCurrentUser: () => ({ data: h.me }) }));
vi.mock("@/shared/hooks/use-orgs", () => ({
  useOrgName: () => (id: string | null | undefined) =>
    ({ "org-tamu": "Texas A&M University", "org-partner": "Partner Lab" })[id ?? ""] ?? "",
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({
    data: [
      { user_id: "u-reg", name: "A. Kumar", org_id: "org-tamu" },
      { user_id: "u-jane", name: "J. Ortiz", org_id: "org-partner" },
    ],
  }),
  useMemberNames: () => (id: string | null | undefined) =>
    ({ "u-reg": "A. Kumar", "u-jane": "J. Ortiz", "u-admin": "R. Lee" })[id ?? ""] ?? "",
}));
vi.mock("@/features/audit/hooks/use-audit", () => ({
  useAuditByEntity: () => ({ data: h.audit }),
}));
vi.mock("@/shared/components/member-selector", () => ({
  MemberSelector: ({
    onSelect,
  }: {
    onSelect: (id: string | null, member?: { user_id: string; org_id: string }) => void;
  }) => (
    <>
      <button type="button" onClick={() => onSelect("u-jane")}>
        pick J. Ortiz
      </button>
      <button
        type="button"
        onClick={() => onSelect("u-far", { user_id: "u-far", org_id: "org-far" })}
      >
        pick a member beyond the first page
      </button>
    </>
  ),
}));
vi.mock("@/shared/components/duar-org-select", () => ({
  DuarOrgSelect: ({
    value,
    onValueChange,
  }: {
    value: string | null;
    onValueChange: (v: string | null) => void;
  }) => (
    <>
      <output aria-label="Org">{value}</output>
      <button type="button" onClick={() => onValueChange("org-partner")}>
        pick Partner Lab
      </button>
    </>
  ),
}));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...a: unknown[]) => h.put(...a),
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import { DisclosureTab } from "./disclosure-tab";

function molecule(overrides: Partial<Molecule> = {}): Molecule {
  return {
    id: "m1",
    workspace_id: "ws",
    registration_number: "CC-004211",
    name: "Cpd",
    molecule_type: "small_molecule",
    structure: null,
    descriptors: null,
    molecular_formula: null,
    structure_status: "disclosed",
    registration_status: "approved",
    synthesis_status: "synthesized",
    lifecycle_stage: "registered",
    stereochemistry: null,
    invention_date: null,
    disclosed_at: "2026-11-12T14:05:00Z",
    disclosure_date: "2026-11-03",
    merged_into_id: null,
    custom_fields: null,
    created_at: "2026-11-12T14:05:00Z",
    registered_by: "u-reg",
    registered_by_org_id: "org-tamu",
    disclosed_by: "u-reg",
    disclosed_by_org_id: "org-tamu",
    identifiers: [],
    version: 1,
    ...overrides,
  };
}

function renderTab(mol: Molecule) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
  );
  return render(<DisclosureTab molecule={mol} />, { wrapper });
}

beforeEach(() => {
  h.me = { user_id: "u-reg", is_admin: false, org_id: "org-tamu", workspace_role: "editor" };
  h.audit = [];
  h.put.mockClear();
});

describe("DisclosureTab", () => {
  it("shows registrant and discloser with org names", () => {
    renderTab(molecule());
    const disclosed = screen.getByRole("region", { name: "Disclosed by" });
    const registered = screen.getByRole("region", { name: "Registered by" });
    expect(disclosed).toHaveTextContent("A. Kumar");
    expect(disclosed).toHaveTextContent("Texas A&M University");
    expect(registered).toHaveTextContent("A. Kumar");
    expect(registered).toHaveTextContent("Texas A&M University");
  });

  it("undisclosed compound shows not disclosed yet and the disclose action", () => {
    renderTab(
      molecule({ structure_status: "undisclosed", disclosed_by: null, disclosed_by_org_id: null }),
    );
    expect(screen.getByText(/not disclosed yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /disclose structure/i }));
    expect(h.push).toHaveBeenCalledWith("/compounds/register?disclose=m1");
  });

  it("change is shown to the registrant and to an admin, not to another editor", () => {
    const { unmount } = renderTab(molecule());
    expect(screen.getByRole("button", { name: /change/i })).toBeInTheDocument();
    unmount();
    h.me = { user_id: "u-admin", is_admin: true, org_id: "org-tamu", workspace_role: "admin" };
    const second = renderTab(molecule());
    expect(screen.getByRole("button", { name: /change/i })).toBeInTheDocument();
    second.unmount();
    h.me = { user_id: "u-other", is_admin: false, org_id: "org-tamu", workspace_role: "editor" };
    renderTab(molecule());
    expect(screen.queryByRole("button", { name: /change/i })).toBeNull();
  });

  it("picking a member fills in their org", () => {
    renderTab(molecule());
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick J. Ortiz" }));
    expect(screen.getByLabelText("Org")).toHaveTextContent("org-partner");
  });

  it("save sends the picked person and org", async () => {
    renderTab(molecule());
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick J. Ortiz" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(h.put).toHaveBeenCalled());
    expect(h.put.mock.calls[0][0]).toMatchObject({
      url: "/api/v1/molecules/m1/discloser",
      method: "PUT",
      data: { disclosed_by: "u-jane", disclosed_by_org_id: "org-partner" },
    });
  });

  it("lists discloser changes from history", () => {
    h.audit = [
      {
        id: "op1",
        performed_by: "u-admin",
        performed_at: "2026-11-20T16:40:00Z",
        entries: [
          { field_name: "event", old_value: null, new_value: "MoleculeDiscloserChanged" },
          { field_name: "disclosed_by_org_id", old_value: "org-tamu", new_value: "org-partner" },
        ],
      },
      { id: "op0", performed_by: "u-reg", performed_at: "2026-11-12T14:05:00Z", entries: [] },
    ];
    renderTab(molecule());
    const list = screen.getByRole("list", { name: /changes to the discloser/i });
    expect(list.querySelectorAll("li")).toHaveLength(1);
    expect(list).toHaveTextContent("R. Lee");
    expect(list).toHaveTextContent("Texas A&M University");
    expect(list).toHaveTextContent("Partner Lab");
  });

  it("picking a member outside the first page still fills in their org", () => {
    renderTab(molecule());
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick a member beyond the first page" }));
    expect(screen.getByLabelText("Org")).toHaveTextContent("org-far");
  });

  it("an org-only change can be saved when no person is on file", async () => {
    h.me = { user_id: "u-admin", is_admin: true, org_id: "org-tamu", workspace_role: "admin" };
    renderTab(molecule({ disclosed_by: null, registered_by: null }));
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick Partner Lab" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(h.put).toHaveBeenCalled());
    expect(h.put.mock.calls[0][0].data).toEqual({ disclosed_by_org_id: "org-partner" });
  });
});
