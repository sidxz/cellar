import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SimilarProtocol } from "../hooks/use-similar-protocols";
import { SimilarProtocolsPanel } from "./similar-protocols-panel";

const match: SimilarProtocol = {
  id: "p1",
  name: "RNAP core IC50",
  protocol_type: "biochemical",
  status: "active",
  score: 0.82,
  is_run_candidate: true,
  shared_readout_kinds: ["ic50"],
  targets: [{ id: "t1", name: "RNAP", target_type: "protein" }],
};

const data = vi.fn<[], SimilarProtocol[]>(() => [match]);
vi.mock("../hooks/use-similar-protocols", async () => ({
  ...(await vi.importActual<object>("../hooks/use-similar-protocols")),
  useSimilarProtocols: () => ({ data: data() }),
}));

describe("SimilarProtocolsPanel", () => {
  it("fires onLogRun for a run candidate", () => {
    const onLogRun = vi.fn();
    render(<SimilarProtocolsPanel draft={{ name: "RNAP core IC50" }} onLogRun={onLogRun} />);
    fireEvent.click(screen.getByText("Log a run of this"));
    expect(onLogRun).toHaveBeenCalledWith("p1");
  });

  it("hides after dismiss", () => {
    render(<SimilarProtocolsPanel draft={{ name: "RNAP core IC50" }} onLogRun={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Dismiss suggestions"));
    expect(screen.queryByText("RNAP core IC50")).not.toBeInTheDocument();
  });
});
