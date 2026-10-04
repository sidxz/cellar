import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RouteAccess } from "./route-access";

const auth = vi.hoisted(() => ({ pathname: "/", role: "viewer" }));
const RANK = ["viewer", "editor", "admin", "owner"];

vi.mock("next/navigation", () => ({ usePathname: () => auth.pathname }));
vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: (min: string) => RANK.indexOf(auth.role) >= RANK.indexOf(min),
}));

function renderAt(pathname: string, role: string) {
  auth.pathname = pathname;
  auth.role = role;
  return render(
    <RouteAccess>
      <p>page body</p>
    </RouteAccess>,
  );
}

describe("RouteAccess", () => {
  it("shows a notice instead of a page that needs a higher role", () => {
    renderAt("/admin/protocol-forms", "editor");
    expect(screen.queryByText("page body")).toBeNull();
    expect(screen.getByText("You don't have access to this page")).toBeInTheDocument();
  });

  it("renders the page for a role that meets its requirement", () => {
    renderAt("/admin/protocol-forms", "admin");
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("keeps pages without a requirement open to viewers", () => {
    renderAt("/admin/audit", "viewer");
    expect(screen.getByText("page body")).toBeInTheDocument();
  });
});
