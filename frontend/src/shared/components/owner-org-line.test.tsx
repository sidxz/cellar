import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OwnerOrgLine } from "./owner-org-line";

vi.mock("@/shared/hooks/use-orgs", () => ({
  useOrgName: () => (id: string | null | undefined) =>
    ({ "org-tamu": "Texas A&M University", "org-partner": "Partner Lab" })[id ?? ""] ?? "",
}));

// The picker itself is covered by SearchableSelect; here it is a plain select.
vi.mock("./duar-org-select", () => ({
  DuarOrgSelect: ({
    value,
    onValueChange,
  }: {
    value: string | null;
    onValueChange: (v: string | null) => void;
  }) => (
    <select aria-label="Org" value={value ?? ""} onChange={(e) => onValueChange(e.target.value)}>
      <option value="org-tamu">Texas A&M University</option>
      <option value="org-partner">Partner Lab</option>
    </select>
  ),
}));

describe("OwnerOrgLine", () => {
  it("shows the owner's name", () => {
    render(<OwnerOrgLine ownerOrgId="org-tamu" canChange={false} onSave={vi.fn()} />);
    expect(screen.getByText("Texas A&M University")).toBeInTheDocument();
  });

  it("a viewer sees no change control", () => {
    render(<OwnerOrgLine ownerOrgId="org-tamu" canChange={false} onSave={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("save is disabled until a different org is picked", () => {
    render(<OwnerOrgLine ownerOrgId="org-tamu" canChange onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /change owner/i }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("save calls onSave with the picked org id", () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<OwnerOrgLine ownerOrgId="org-tamu" canChange onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /change owner/i }));
    fireEvent.change(screen.getByLabelText("Org"), { target: { value: "org-partner" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith("org-partner");
  });

  it("escape cancels without saving", () => {
    const onSave = vi.fn();
    render(<OwnerOrgLine ownerOrgId="org-tamu" canChange onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /change owner/i }));
    fireEvent.keyDown(screen.getByLabelText("Org"), { key: "Escape" });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
