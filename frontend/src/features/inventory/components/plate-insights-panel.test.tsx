import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateInsightsResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlateInsightsPanel } from "./plate-insights-panel";

// Capture Plot props rather than render Plotly — lets tests assert on the
// trace objects (e.g. truncated labels / customdata) without a real chart.
const plotCalls: Array<{ data: Array<Record<string, unknown>> }> = [];
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: { data: Array<Record<string, unknown>> }) => {
    plotCalls.push(p);
    return <div data-testid="plot" />;
  },
}));

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

const FIXTURE: PlateInsightsResponse = {
  org_id: "org-1",
  total_plates: 42,
  open_loans: 5,
  overdue_count: 2,
  by_status: [
    { key: "stored", count: 30 },
    { key: "checked_out", count: 12 },
  ],
  by_type: [
    { key: "compound", count: 40 },
    { key: "control", count: 2 },
  ],
  by_location: [
    { name: "Freezer A", count: 20 },
    { name: "Freezer B", count: 22 },
  ],
  group_sizes: [
    { group_id: "grp-1", name: "Vendor Library", count: 15 },
    { group_id: "grp-2", name: "In-house", count: 27 },
  ],
  loan_activity_weekly: Array.from({ length: 12 }, (_, i) => ({
    week_start: `2026-W${i + 1}`,
    requested: i,
    returned: Math.max(i - 1, 0),
  })),
};

function setup(orgId: string | undefined, response: PlateInsightsResponse = FIXTURE) {
  mocked.mockImplementation((opts: unknown) => {
    const { url } = opts as { url: string };
    if (url !== "/api/v1/plates/insights") {
      return Promise.reject(new Error(`unexpected url: ${url}`));
    }
    return Promise.resolve(response);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PlateInsightsPanel orgId={orgId} />, { wrapper });
}

describe("PlateInsightsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    plotCalls.length = 0;
  });

  it("renders the three stat tiles, overdue styled destructive when > 0", async () => {
    setup("org-1");
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("2")).toHaveClass("text-destructive");
  });

  it("renders five plots when data is present", async () => {
    setup("org-1");
    await screen.findByText("42");
    expect(screen.getAllByTestId("plot")).toHaveLength(5);
  });

  it("shows the empty state and zero plots when total_plates is 0", async () => {
    setup("org-1", { ...FIXTURE, total_plates: 0 });
    expect(await screen.findByText("No plates for this organization yet.")).toBeInTheDocument();
    expect(screen.queryAllByTestId("plot")).toHaveLength(0);
  });

  it("does not fetch when orgId is undefined", () => {
    setup(undefined);
    expect(customInstance).not.toHaveBeenCalled();
  });

  it("truncates long horizontal-bar labels to 24 chars, keeps full name in customdata for hover", async () => {
    const longName = "sac1-hit_collection-NaOAc_384well_extra_long";
    setup("org-1", {
      ...FIXTURE,
      by_location: [{ name: longName, count: 9 }],
      group_sizes: [{ group_id: "grp-9", name: longName, count: 9 }],
    });
    await screen.findByText("42");

    const expectedTick = `${longName.slice(0, 23)}…`;
    const hovertemplate = "%{customdata}: %{x}<extra></extra>";

    // plotCalls order matches render order: status, type, loan activity,
    // storage occupancy (by_location), top groups (group_sizes).
    const locationTrace = plotCalls[3].data[0];
    expect(locationTrace.y).toEqual([expectedTick]);
    expect(locationTrace.customdata).toEqual([longName]);
    expect(locationTrace.hovertemplate).toBe(hovertemplate);

    const groupTrace = plotCalls[4].data[0];
    expect(groupTrace.y).toEqual([expectedTick]);
    expect(groupTrace.customdata).toEqual([longName]);
    expect(groupTrace.hovertemplate).toBe(hovertemplate);
  });
});
