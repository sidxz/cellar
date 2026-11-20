import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WizardStepIndicator } from "./wizard-step-indicator";

describe("WizardStepIndicator", () => {
  const steps = ["Upload", "Mapping", "Preview", "Confirm"];

  it("renders nothing when there are no steps", () => {
    const { container } = render(<WizardStepIndicator steps={[]} current={1} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders one numbered circle and label per step", () => {
    render(<WizardStepIndicator steps={steps} current={2} />);
    for (const label of steps) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // Step numbers 1..4 are rendered.
    for (let n = 1; n <= steps.length; n++) {
      expect(screen.getByText(String(n))).toBeInTheDocument();
    }
  });

  it("marks steps before the current one complete and the current one as the current step", () => {
    render(<WizardStepIndicator steps={steps} current={3} />);
    const step = (label: string) => screen.getByText(label).closest("[data-state]");
    expect(steps.map((label) => step(label)?.getAttribute("data-state"))).toEqual([
      "complete",
      "complete",
      "active",
      "upcoming",
    ]);
    expect(steps.map((label) => step(label)?.getAttribute("aria-current"))).toEqual([
      null,
      null,
      "step",
      null,
    ]);
  });

  it("exposes a navigation landmark for the step strip", () => {
    render(<WizardStepIndicator steps={steps} current={1} />);
    expect(screen.getByRole("navigation", { name: /wizard steps/i })).toBeInTheDocument();
  });
});
