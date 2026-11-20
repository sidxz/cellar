import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { bulkStepIndex } from "../../types/registration-wizard";
import { RegistrationWizard } from "./registration-wizard";

const h = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => h.params,
  useRouter: () => ({ push: h.push }),
}));
vi.mock("../../hooks/use-collection-import-handoff", () => ({
  useCollectionImportHandoff: () => {},
}));
vi.mock("./step-input", () => ({ StepInput: () => <div>Upload screen</div> }));
vi.mock("./step-mapping", () => ({ StepMapping: () => <div>Mapping screen</div> }));
vi.mock("./step-preview", () => ({ StepPreview: () => <div>Review screen</div> }));
vi.mock("./step-processing", () => ({ StepProcessing: () => <div>Existing registration</div> }));
vi.mock("./step-results", () => ({ StepResults: () => null }));
vi.mock("./step-summary", () => ({ StepSummary: () => null }));
vi.mock("./step-batch", () => ({ StepBatch: () => null }));

beforeEach(() => {
  useRegistrationWizard.getState().reset();
  h.params = new URLSearchParams();
  window.history.replaceState(null, "", "/compounds/register");
});
describe("Bulk registration navigation", () => {
  it("shows four stages and restores an existing registration from its address", () => {
    h.params = new URLSearchParams("mode=bulk&workflow_id=bulk-reg-1");
    const page = render(<RegistrationWizard />);
    expect(screen.getByText("Review & register")).toBeVisible();
    expect(screen.getByText("Existing registration")).toBeVisible();
    expect(useRegistrationWizard.getState().workflowId).toBe("bulk-reg-1");
    expect(useRegistrationWizard.getState().currentStep).toBe(bulkStepIndex("Processing"));
    expect(window.location.search).toContain("workflow_id=bulk-reg-1");
    page.unmount();
    expect(useRegistrationWizard.getState().workflowId).toBe("bulk-reg-1");
  });

  it("rejects a workflow address containing path traversal", () => {
    h.params = new URLSearchParams("mode=bulk&workflow_id=../../molecules");
    render(<RegistrationWizard />);
    expect(useRegistrationWizard.getState().workflowId).toBeNull();
    expect(screen.getByText("Upload screen")).toBeVisible();
  });
});
