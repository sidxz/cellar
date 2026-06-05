import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CurveEditHistoryEventBody } from "@/shared/lib/api/model";
import { CurveEditHistory } from "./curve-edit-history";

const events: CurveEditHistoryEventBody[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    operation_type: "curve_point_exclusion",
    user_id: "abcdef12-3456-7890-abcd-ef1234567890",
    // 30 days ago → "Xw ago" via formatRelativeDate (weeks bucket)
    timestamp: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    reason: "outlier: lid dropped on plate",
    entries: [
      {
        field_name: "excluded_points",
        old_value: "[]",
        new_value: "[{...}]",
      },
    ],
  },
];

describe("<CurveEditHistory />", () => {
  it("renders 'No edit history yet' when events is empty", () => {
    render(<CurveEditHistory events={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /view edit history/i }));
    expect(screen.getByText(/no edit history/i)).toBeInTheDocument();
  });

  it("renders each event with reason and a relative timestamp", () => {
    render(<CurveEditHistory events={events} />);
    fireEvent.click(screen.getByRole("button", { name: /view edit history/i }));
    expect(screen.getByText(/lid dropped on plate/i)).toBeInTheDocument();
    // formatRelativeDate uses "Xw ago" / "Xd ago" / "yesterday" / etc.
    expect(screen.getByText(/ago/i)).toBeInTheDocument();
    // Short user-id prefix (Task 3.1 doesn't resolve to display name).
    expect(screen.getByText(/by abcdef12/i)).toBeInTheDocument();
  });

  it("shows the loading state instead of the list when isLoading", () => {
    render(<CurveEditHistory events={[]} isLoading />);
    fireEvent.click(screen.getByRole("button", { name: /view edit history/i }));
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText(/no edit history/i)).toBeNull();
  });

  it("falls back to 'Edit' when reason is null", () => {
    const noReason: CurveEditHistoryEventBody[] = [
      { ...events[0], reason: null, id: "22222222-2222-2222-2222-222222222222" },
    ];
    render(<CurveEditHistory events={noReason} />);
    fireEvent.click(screen.getByRole("button", { name: /view edit history/i }));
    expect(screen.getByText(/^Edit$/)).toBeInTheDocument();
  });

  it("omits the 'by …' suffix when user_id is null", () => {
    const noUser: CurveEditHistoryEventBody[] = [
      { ...events[0], user_id: null, id: "33333333-3333-3333-3333-333333333333" },
    ];
    render(<CurveEditHistory events={noUser} />);
    fireEvent.click(screen.getByRole("button", { name: /view edit history/i }));
    expect(screen.queryByText(/by /i)).toBeNull();
  });
});
