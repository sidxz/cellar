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

  it("styles steps before the current one as completed and the current one as active", () => {
    render(<WizardStepIndicator steps={steps} current={3} />);
    // Step 1 and 2 done (green); step 3 active (primary); step 4 upcoming (muted).
    expect(screen.getByText("1").className).toContain("border-green-500");
    expect(screen.getByText("2").className).toContain("border-green-500");
    expect(screen.getByText("3").className).toContain("border-primary");
    expect(screen.getByText("4").className).toContain("border-muted");
  });

  it("exposes a navigation landmark for the step strip", () => {
    render(<WizardStepIndicator steps={steps} current={1} />);
    expect(screen.getByRole("navigation", { name: /wizard steps/i })).toBeInTheDocument();
  });
});
