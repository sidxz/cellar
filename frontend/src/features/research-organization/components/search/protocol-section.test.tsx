import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { ActivityCriterion } from "../../types";
import {
  type ProtocolConjunction,
  ProtocolSection,
  pickProtocolCriterion,
} from "./protocol-section";

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: () => ({ data: undefined }),
  useProtocolSummaries: () => ({ data: [] }),
}));
vi.mock("./run-scope-picker", () => ({ RunScopePicker: () => null }));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => false);
  Element.prototype.releasePointerCapture = vi.fn();
});

function Harness({ initialJoins }: { initialJoins: ProtocolConjunction[] }) {
  const [criteria, setCriteria] = useState<ActivityCriterion[]>(
    initialJoins.map((_, i) => ({ type: "activity", protocol_id: `p${i}`, where: [] })),
  );
  const [joins, setJoins] = useState(initialJoins);
  return (
    <>
      <ProtocolSection
        criteria={criteria}
        conjunctions={joins}
        protocols={[]}
        projectIds={[]}
        onChange={(next, nextJoins) => {
          setCriteria(next);
          setJoins(nextJoins);
        }}
      />
      <output data-testid="joins">{JSON.stringify(joins)}</output>
    </>
  );
}

function chooseMode(label: string) {
  fireEvent.click(screen.getByRole("combobox", { name: "Assay matching" }));
  fireEvent.click(screen.getByRole("option", { name: label }));
}

describe("assay matching controls", () => {
  it("switches to all assays and keeps new assays joined with AND", () => {
    render(<Harness initialJoins={["or", "or"]} />);
    chooseMode("Match all assays");
    expect(screen.getByTestId("joins")).toHaveTextContent('["and","and"]');
    fireEvent.click(screen.getByRole("button", { name: "Add another assay" }));
    expect(screen.getByTestId("joins")).toHaveTextContent('["and","and","and"]');
    expect(screen.queryByRole("combobox", { name: "Join assay 2" })).not.toBeInTheDocument();
  });

  it("switches every assay to OR when choosing any assay", () => {
    render(<Harness initialJoins={["and", "and", "and"]} />);
    chooseMode("Match any assay");
    expect(screen.getByTestId("joins")).toHaveTextContent('["or","or","or"]');
  });

  it("shows saved mixed logic without rewriting it", () => {
    render(<Harness initialJoins={["and", "and", "or"]} />);
    expect(screen.getByRole("combobox", { name: "Assay matching" })).toHaveTextContent(
      "Custom logic",
    );
    expect(screen.getByRole("combobox", { name: "Join assay 2" })).toHaveTextContent("and");
    expect(screen.getByRole("combobox", { name: "Join assay 3" })).toHaveTextContent("or");
    expect(screen.getByTestId("joins")).toHaveTextContent('["and","and","or"]');
  });

  it("opens custom logic without changing a uniform search", () => {
    render(<Harness initialJoins={["or", "or"]} />);
    chooseMode("Custom logic");
    expect(screen.getByRole("combobox", { name: "Join assay 2" })).toBeVisible();
    expect(screen.getByTestId("joins")).toHaveTextContent('["or","or"]');
  });
});

describe("pickProtocolCriterion", () => {
  it("drops the split and hand-picked runs, which belong to the old protocol", () => {
    const before: ActivityCriterion = {
      type: "activity",
      protocol_id: "p1",
      where: [],
      run_scope: { mode: "specific", run_ids: ["r1"] },
      split: { by: "run" },
    };
    const after = pickProtocolCriterion(before, "p2");
    expect(after.protocol_id).toBe("p2");
    expect(after.split).toBeUndefined();
    expect(after.run_scope).toBeUndefined();
  });

  it("keeps a run filter that isn't tied to particular runs", () => {
    const before: ActivityCriterion = {
      type: "activity",
      protocol_id: "p1",
      where: [],
      run_scope: { mode: "latest" },
    };
    expect(pickProtocolCriterion(before, "p2").run_scope).toEqual({ mode: "latest" });
  });
});

describe("two rows on one protocol", () => {
  it("flags a second row whose run filter disagrees with the first", () => {
    render(
      <ProtocolSection
        criteria={[
          { type: "activity", protocol_id: "p1", where: [], run_scope: { mode: "latest" } },
          { type: "activity", protocol_id: "p1", where: [] },
        ]}
        conjunctions={["or", "or"]}
        protocols={[]}
        projectIds={[]}
        onChange={() => {}}
      />,
    );
    expect(
      screen.getAllByText("This protocol already has a different run filter or split above."),
    ).toHaveLength(1);
  });

  it("doesn't flag rows that agree", () => {
    render(
      <ProtocolSection
        criteria={[
          { type: "activity", protocol_id: "p1", where: [] },
          { type: "activity", protocol_id: "p1", where: [] },
        ]}
        conjunctions={["or", "or"]}
        protocols={[]}
        projectIds={[]}
        onChange={() => {}}
      />,
    );
    expect(
      screen.queryByText("This protocol already has a different run filter or split above."),
    ).toBeNull();
  });
});

describe("removing an assay", () => {
  it("offers no per-assay remove on the only assay — the section's × covers it", () => {
    render(<Harness initialJoins={["or"]} />);
    expect(screen.queryByRole("button", { name: "Remove assay 1" })).toBeNull();
  });

  it("offers a remove on each assay once there are two", () => {
    render(<Harness initialJoins={["or", "or"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove assay 2" }));
    expect(screen.getByTestId("joins")).toHaveTextContent('["or"]');
    expect(screen.queryByRole("button", { name: "Remove assay 1" })).toBeNull();
  });
});
