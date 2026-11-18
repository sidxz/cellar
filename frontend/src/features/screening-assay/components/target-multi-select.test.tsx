import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { TargetMultiSelect } from "./target-multi-select";

// Radix Popover/Command items need pointer-event stubs in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

vi.mock("../hooks/use-targets", () => ({
  useTargets: () => ({
    data: [
      { id: "t-1", name: "EGFR", target_type: "single_protein", organism: "Homo sapiens" },
      { id: "t-2", name: "BRAF", target_type: "single_protein", organism: "Homo sapiens" },
      { id: "t-3", name: "DHODH", target_type: "single_protein", organism: "Homo sapiens" },
      {
        id: "t-4",
        name: "DHODH",
        target_type: "single_protein",
        organism: "Plasmodium falciparum",
      },
    ],
  }),
}));

// The real dialog is covered in request-target-dialog.test.tsx; this stand-in "creates" one.
vi.mock("./request-target-dialog", () => ({
  RequestTargetDialog: ({
    open,
    onCreated,
  }: {
    open: boolean;
    onCreated: (t: { id: string; name: string }) => void;
  }) =>
    open ? (
      <button type="button" onClick={() => onCreated({ id: "t-new", name: "hERG" })}>
        create hERG
      </button>
    ) : null,
}));

// The trigger sets role="combobox" (mirrors SearchableSelect), so it is
// queried as a combobox — not a button.
function openPopover() {
  fireEvent.click(screen.getByRole("combobox"));
}

describe("TargetMultiSelect", () => {
  it("trigger shows the placeholder when nothing is selected", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    // A combobox-role element takes its accessible name from a label, not its
    // text, so assert the visible trigger text directly.
    expect(screen.getByText(/select targets/i)).toBeInTheDocument();
  });

  it("trigger shows a count when targets are selected", () => {
    render(<TargetMultiSelect value={["t-1"]} onChange={vi.fn()} />);
    expect(screen.getByText(/1 target selected/i)).toBeInTheDocument();
  });

  it("opening the popover lists the available targets and a search box", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    expect(screen.getByPlaceholderText(/search targets/i)).toBeInTheDocument();
    expect(screen.getByText("EGFR")).toBeInTheDocument();
    expect(screen.getByText("BRAF")).toBeInTheDocument();
    // The inline "Manage in Prot-Cellar" affordance is offered too.
    expect(screen.getByText(/manage in prot-cellar/i)).toBeInTheDocument();
  });

  it("selecting a target adds its id via onChange", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={[]} onChange={onChange} />);
    openPopover();
    const item = screen.getByText("EGFR").closest("[data-slot='command-item']") as HTMLElement;
    expect(item).not.toBeNull();
    fireEvent.click(item);
    expect(onChange).toHaveBeenCalledWith(["t-1"]);
  });

  it("selecting an already-selected target removes it (toggle)", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={["t-1"]} onChange={onChange} />);
    openPopover();
    // "EGFR" appears twice when selected (the popover option + the chip), so
    // scope the click to the command-item, not the chip badge.
    const item = screen
      .getAllByText("EGFR")
      .map((el) => el.closest("[data-slot='command-item']"))
      .find((el): el is HTMLElement => el !== null);
    expect(item).toBeTruthy();
    fireEvent.click(item as HTMLElement);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("removing a selected chip calls onChange without that id", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={["t-1", "t-2"]} onChange={onChange} />);
    // Each selected target renders a removable chip with an aria-labelled button.
    fireEvent.click(screen.getByRole("button", { name: /remove egfr/i }));
    expect(onChange).toHaveBeenCalledWith(["t-2"]);
  });

  it("'Manage in Prot-Cellar' opens the catalog in a new tab", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    const item = screen
      .getByText(/manage in prot-cellar/i)
      .closest("[data-slot='command-item']") as HTMLElement;
    fireEvent.click(item);
    expect(open).toHaveBeenCalledWith(
      "http://localhost:3001/targets",
      "_blank",
      "noopener,noreferrer",
    );
    open.mockRestore();
  });

  it("tells same-named targets apart by organism", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={[]} onChange={onChange} />);
    openPopover();
    const pf = screen.getByText("Plasmodium falciparum").closest("[data-slot='command-item']");
    expect(pf).toHaveTextContent("DHODH");
    fireEvent.click(pf as HTMLElement);
    expect(onChange).toHaveBeenCalledWith(["t-4"]);
  });

  it("search keeps only targets that contain what was typed", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    // Fuzzy matching also kept EGFR: an "r" in the name, then an "a" in "Homo sapiens".
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), { target: { value: "ra" } });
    expect(screen.getByText("BRAF")).toBeInTheDocument();
    expect(screen.queryByText("EGFR")).not.toBeInTheDocument();
    expect(screen.queryByText("DHODH")).not.toBeInTheDocument();
  });

  it("search never matches a target by its internal id", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), { target: { value: "t-1" } });
    expect(screen.queryByText("EGFR")).not.toBeInTheDocument();
    expect(screen.getByText(/no targets found/i)).toBeInTheDocument();
  });

  it("search finds a target by organism", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), {
      target: { value: "dhodh plasmodium" },
    });
    expect(screen.getByText("Plasmodium falciparum")).toBeInTheDocument();
    expect(screen.queryByText("Homo sapiens")).not.toBeInTheDocument();
  });

  it("'Request a new target' stays visible when the search finds nothing", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), {
      target: { value: "hERG" },
    });
    expect(screen.getByText(/request a new target/i)).toBeVisible();
  });

  it("lists matches above the actions and highlights the top match", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), { target: { value: "ra" } });
    const rows = [...document.querySelectorAll("[data-slot='command-item']")];
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("BRAF"),
      "Request a new target",
      "Manage in Prot-Cellar",
    ]);
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
  });

  it("'Request a new target' opens the dialog and selects the created target", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={["t-1"]} onChange={onChange} />);
    openPopover();
    fireEvent.change(screen.getByPlaceholderText(/search targets/i), {
      target: { value: "hERG" },
    });
    const item = screen
      .getByText(/request a new target/i)
      .closest("[data-slot='command-item']") as HTMLElement;
    fireEvent.click(item);
    fireEvent.click(screen.getByRole("button", { name: "create hERG" }));
    expect(onChange).toHaveBeenCalledWith(["t-1", "t-new"]);
    expect(screen.queryByRole("button", { name: "create hERG" })).not.toBeInTheDocument();
  });
});
