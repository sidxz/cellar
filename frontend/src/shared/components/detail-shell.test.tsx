import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailShell } from "./detail-shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/assays/protocols/p-1" }));
vi.mock("@/shared/lib/stores/breadcrumb-store", () => ({
  useBreadcrumbTrail: () => undefined,
  useBreadcrumbOverride: () => undefined,
}));

describe("DetailShell subtitle", () => {
  it("renders the subtitle under the title", () => {
    render(
      <DetailShell
        query={{ data: { name: "PptT inhibition [FP]", code: "PRT-00042" }, isLoading: false }}
        title={(e) => e.name}
        subtitle={(e) => <span>{e.code}</span>}
      >
        {() => null}
      </DetailShell>,
    );
    expect(screen.getByRole("heading", { name: "PptT inhibition [FP]" })).toBeInTheDocument();
    expect(screen.getByText("PRT-00042")).toBeInTheDocument();
  });
});
