import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceSettingsForm } from "./workspace-settings-form";

const mutateAsync = vi.hoisted(() => vi.fn());

const { settings } = vi.hoisted(() => ({
  // Stable reference: the form re-seeds itself whenever `settings` changes identity.
  settings: {
    registration_rules: {},
    custom_field_definitions: [],
    default_molecule_type: null,
    audit_reason_policy: "never",
    signature_required_for: [],
    audit_retention_days: null,
    formulation_number_scheme: null,
    protocol_naming: { code_prefix: "ASY-", code_width: 4 },
    version: 1,
  },
}));

vi.mock("../hooks/use-workspace-settings", () => ({
  useWorkspaceSettings: () => ({ data: settings, isLoading: false }),
  useUpdateWorkspaceSettings: () => ({ mutateAsync, isPending: false }),
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/settings" }));
vi.mock("./custom-field-builder", () => ({ CustomFieldBuilder: () => null }));

describe("WorkspaceSettingsForm protocol codes", () => {
  beforeEach(() => mutateAsync.mockReset());

  it("seeds and saves the protocol code prefix and width", async () => {
    render(<WorkspaceSettingsForm />);
    const prefix = screen.getByLabelText("Protocol Code Prefix") as HTMLInputElement;
    await waitFor(() => expect(prefix.value).toBe("ASY-"));
    expect((screen.getByLabelText("Protocol Code Width") as HTMLInputElement).value).toBe("4");

    fireEvent.change(prefix, { target: { value: "PRT-" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].protocol_naming).toEqual({
      code_prefix: "PRT-",
      code_width: 4,
    });
  });
});
