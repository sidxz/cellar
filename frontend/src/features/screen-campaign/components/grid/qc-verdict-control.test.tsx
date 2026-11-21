import type { CampaignMeasurementResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QcMark, QcVerdictControl } from "./qc-verdict-control";

const { mutate, hook } = vi.hoisted(() => ({
  mutate: vi.fn(),
  hook: { options: undefined as { mutation?: { onSuccess?: () => void } } | undefined },
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut: (options: typeof hook.options) => {
    hook.options = options;
    return { mutate, isPending: false };
  },
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

function renderControl(
  measurement: CampaignMeasurementResponse,
  readOnly = false,
  qc = new QueryClient(),
) {
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
    expect(mutate.mock.calls[0]).toEqual([
      {
        campaignId: "c1",
        data: {
          verdict: "verified",
          targets: [{ channel_ids: ["ch-1"], result_ids: ["r1"] }],
          overwrite: true,
        },
      },
    ]);
  });

  it("switching to the other verdict never carries the old note", () => {
    renderControl(m({ qc_verdict: "verified", qc_verdict_note: "clean curve" }));
    fireEvent.click(screen.getByRole("button", { name: "Failed" }));
    expect(mutate.mock.calls[0][0].data).not.toHaveProperty("note");
  });

  it("sends the note with the verdict on Save", () => {
    renderControl(m({ qc_verdict: "verified" }));
    fireEvent.change(screen.getByPlaceholderText("Note (optional)"), { target: { value: "ok" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate.mock.calls[0][0].data).toMatchObject({
      verdict: "verified",
      overwrite: true,
      note: "ok",
    });
  });

  it("Save with the note emptied sends null, which removes it", () => {
    renderControl(m({ qc_verdict: "failed", qc_verdict_note: "edge well" }));
    fireEvent.change(screen.getByPlaceholderText("Note (optional)"), { target: { value: " " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate.mock.calls[0][0].data).toMatchObject({ verdict: "failed", note: null });
  });

  it("refreshes the campaign from the hook, so a closed card still refreshes", () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    renderControl(m(), false, qc);
    hook.options?.mutation?.onSuccess?.();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["campaigns", "detail", "c1"] });
  });

  it("shows the label with who and when, and no buttons, when read-only", () => {
    renderControl(
      m({ qc_verdict: "failed", qc_verdict_by: "u1", qc_verdict_at: "2026-11-20T10:00:00Z" }),
      true,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/^by Ada · \S+/)).toBeInTheDocument();
  });

  it("shows who and when beside the verdict buttons", () => {
    renderControl(m({ qc_verdict: "verified", qc_verdict_by: "u1", qc_verdict_at: "2026-11-20" }));
    expect(screen.getByText(/^by Ada · \S+/)).toBeInTheDocument();
  });

  it("shows no stamp on a not-tested cell", () => {
    renderControl(m(), true);
    expect(screen.queryByText(/^by /)).toBeNull();
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
