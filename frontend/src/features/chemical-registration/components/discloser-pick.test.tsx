import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DiscloserPick } from "./discloser-pick";

vi.mock("@/shared/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { user_id: "u-me", org_id: "org-tamu" } }),
}));
vi.mock("@/shared/hooks/use-orgs", () => ({
  useOrgName: () => (id: string | null | undefined) =>
    ({ "org-tamu": "Texas A&M University", "org-partner": "Partner Lab" })[id ?? ""] ?? "",
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({
    data: [{ user_id: "u-jane", name: "J. Ortiz", org_id: "org-partner" }],
  }),
  useMemberNames: () => (id: string | null | undefined) =>
    ({ "u-jane": "J. Ortiz" })[id ?? ""] ?? "",
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
  DuarOrgSelect: () => <span />,
}));

describe("DiscloserPick", () => {
  it("defaults to you and your org", () => {
    render(<DiscloserPick value={{ userId: null, orgId: null }} onChange={vi.fn()} />);
    expect(screen.getByText(/you · Texas A&M University/i)).toBeInTheDocument();
  });

  it("picking a member sets them and their org", () => {
    const onChange = vi.fn();
    render(<DiscloserPick value={{ userId: null, orgId: null }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick J. Ortiz" }));
    expect(onChange).toHaveBeenCalledWith({ userId: "u-jane", orgId: "org-partner" });
  });

  it("picking a member outside the first page still sets their org", () => {
    const onChange = vi.fn();
    render(<DiscloserPick value={{ userId: null, orgId: null }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /change/i }));
    fireEvent.click(screen.getByRole("button", { name: "pick a member beyond the first page" }));
    expect(onChange).toHaveBeenCalledWith({ userId: "u-far", orgId: "org-far" });
  });
});
