import { SidebarProvider } from "@/shared/components/ui/sidebar";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NavMain } from "./nav-main";

const auth = vi.hoisted(() => ({ role: "viewer" }));
const RANK = ["viewer", "editor", "admin", "owner"];
const SETUP_SECTIONS = [
  "Screening Setup",
  "Registration Setup",
  "Vocabularies",
  "Organization",
  "Data Import",
];

vi.mock("next/navigation", () => ({ usePathname: () => "/compounds" }));
vi.mock("@/shared/hooks/use-mobile", () => ({ useIsMobile: () => false }));
vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: (min: string) => RANK.indexOf(auth.role) >= RANK.indexOf(min),
}));

function renderAs(role: string) {
  auth.role = role;
  return render(
    <SidebarProvider>
      <NavMain />
    </SidebarProvider>,
  );
}

describe("NavMain", () => {
  it("shows a viewer no setup sections, only the Audit Log under Administration", () => {
    renderAs("viewer");
    expect(screen.getByText("Audit Log")).toBeInTheDocument();
    for (const title of SETUP_SECTIONS) expect(screen.queryByText(title)).toBeNull();
  });

  it("shows an admin every setup section", () => {
    renderAs("admin");
    for (const title of SETUP_SECTIONS) expect(screen.getByText(title)).toBeInTheDocument();
  });
});
