import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProtocolNamesAdmin } from "./protocol-names-admin";

const rederive = vi.fn();
const state = vi.hoisted(() => ({
  flags: [{ protocol_id: "p1", code: "PRT-00007", name: "Legacy assay", flag: "needs_facts" }],
  dryRun: {
    changes: [
      {
        protocol_id: "p2",
        code: "PRT-00002",
        before: "Old hand-typed name",
        after: "M. tuberculosis growth inhibition [resazurin]",
        flag: null,
      },
    ],
    report: null,
  },
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/protocol-names" }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/features/screening-assay/hooks/use-protocol-names-admin", () => ({
  useNameFlags: () => ({ data: state.flags, isLoading: false }),
  useRederiveNames: () => ({
    mutate: (body: { dry_run: boolean }, opts?: { onSuccess?: (r: unknown) => void }) => {
      rederive(body);
      opts?.onSuccess?.(body.dry_run ? state.dryRun : { changes: [], report: { renamed: 1 } });
    },
    isPending: false,
  }),
}));

describe("ProtocolNamesAdmin", () => {
  it("lists protocols whose name needs attention", () => {
    render(<ProtocolNamesAdmin />);
    expect(screen.getByText("PRT-00007")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Legacy assay" })).toHaveAttribute(
      "href",
      "/assays/protocols/p1",
    );
  });

  it("checks all names, shows before and after, and applies on request", () => {
    render(<ProtocolNamesAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /check all names/i }));
    expect(rederive).toHaveBeenLastCalledWith(expect.objectContaining({ dry_run: true }));
    expect(screen.getByText("Old hand-typed name")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(rederive).toHaveBeenLastCalledWith(expect.objectContaining({ dry_run: false }));
  });
});
