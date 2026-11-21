import type { CampaignMeasurementResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QcMark, QcVerdictControl } from "./qc-verdict-control";

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut: () => ({ mutate, isPending: false }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => () => "Ada",
}));
vi.mock("../../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
}));

const m = (over: Partial<CampaignMeasurementResponse> = {}) =>
  ({
    channel_id: "ch-1",
    qc_verdict: "not_tested",
    holds_result: true,
    ...over,
  }) as CampaignMeasurementResponse;

function renderControl(measurement: CampaignMeasurementResponse, readOnly = false) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <QcVerdictControl
        campaignId="c1"
        measurement={measurement}
        resultId="r1"
        readOnly={readOnly}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => mutate.mockClear());

describe("QcVerdictControl", () => {
  it("sends one 1x1 target with overwrite when Verified is clicked", () => {
    renderControl(m());
    fireEvent.click(screen.getByRole("button", { name: "Verified" }));
    expect(mutate).toHaveBeenCalledWith(
      {
        campaignId: "c1",
        data: {
          verdict: "verified",
          targets: [{ channel_ids: ["ch-1"], result_ids: ["r1"] }],
          overwrite: true,
        },
      },
      expect.anything(),
    );
  });

  it("sends the note with the verdict on Save", () => {
    renderControl(m({ qc_verdict: "verified" }));
    fireEvent.change(screen.getByPlaceholderText("Note (optional)"), { target: { value: "ok" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate.mock.calls[0][0].data).toMatchObject({ verdict: "verified", note: "ok" });
  });

  it("shows the label only when read-only", () => {
    renderControl(m({ qc_verdict: "failed" }), true);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders nothing when the cell holds no result", () => {
    const { container } = renderControl(m({ holds_result: false }));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("QcMark", () => {
  it("marks verified and failed, with who and when in the title", () => {
    render(
      <QcMark
        measurement={m({
          qc_verdict: "verified",
          qc_verdict_by: "u1",
          qc_verdict_at: "2026-11-20T10:00:00Z",
          qc_verdict_note: "clean",
        })}
      />,
    );
    const mark = screen.getByLabelText("QC verified");
    expect(mark).toHaveTextContent("✓");
    expect(mark.getAttribute("title")).toMatch(/^Verified by Ada · .+ · clean$/);
  });

  it("renders nothing for not tested", () => {
    const { container } = render(<QcMark measurement={m()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
