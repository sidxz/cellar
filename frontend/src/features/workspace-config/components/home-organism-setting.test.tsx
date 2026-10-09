import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomeOrganismSetting, homeOrganismsFrom } from "./home-organism-setting";

const term = (id: number, label: string) => ({
  term_id: `http://purl.bioontology.org/ontology/NCBITAXON/${id}`,
  label,
  ontology_source: "NCBITAXON",
});
const MTB = term(1773, "Mycobacterium tuberculosis");
const HUMAN = term(9606, "Homo sapiens");

const previewRequests: unknown[] = [];
const setHome = vi.hoisted(() => vi.fn());
vi.mock("../hooks/use-naming-changes", () => ({
  usePreviewNamingChange: () => ({
    mutate: (req: unknown, opts?: { onSuccess?: () => void }) => {
      previewRequests.push(req);
      opts?.onSuccess?.();
    },
    data: { changes: [], collisions: [] },
    isPending: false,
  }),
  useSetHomeOrganism: () => ({ mutateAsync: setHome, isPending: false }),
}));
vi.mock("@/shared/components/ontology-search-input", () => ({
  OntologySearchInput: ({
    value,
    onChange,
  }: {
    value: { label: string }[];
    onChange: (t: unknown[]) => void;
  }) => (
    <div>
      <span data-testid="picked">{value.map((v) => v.label).join("|")}</span>
      <button
        type="button"
        onClick={() =>
          onChange([
            { ...MTB, uri: null },
            { ...HUMAN, uri: null },
          ])
        }
      >
        pick both
      </button>
      <button type="button" onClick={() => onChange([])}>
        clear all
      </button>
    </div>
  ),
}));

describe("HomeOrganismSetting", () => {
  beforeEach(() => {
    previewRequests.length = 0;
    setHome.mockReset();
  });

  it("keeps every organism picked (a list, not one)", () => {
    render(<HomeOrganismSetting current={[MTB, HUMAN]} />);
    expect(screen.getByTestId("picked").textContent).toBe(
      "Mycobacterium tuberculosis|Homo sapiens",
    );
    expect(
      (screen.getByRole("button", { name: /change home organisms/i }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("previews first and saves the list only on Apply", async () => {
    render(<HomeOrganismSetting current={[MTB]} />);
    fireEvent.click(screen.getByRole("button", { name: "pick both" }));
    fireEvent.click(screen.getByRole("button", { name: /change home organisms/i }));
    expect(previewRequests.at(-1)).toEqual({ kind: "home_organism", terms: [MTB, HUMAN] });
    expect(setHome).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(setHome).toHaveBeenCalledWith({ terms: [MTB, HUMAN] }));
  });

  it("can clear them all", () => {
    render(<HomeOrganismSetting current={[MTB]} />);
    fireEvent.click(screen.getByRole("button", { name: "clear all" }));
    fireEvent.click(screen.getByRole("button", { name: /change home organisms/i }));
    expect(previewRequests.at(-1)).toEqual({ kind: "home_organism", terms: [] });
  });
});

describe("homeOrganismsFrom", () => {
  it("reads the list, falling back to the legacy single organism", () => {
    expect(homeOrganismsFrom({ home_organisms: [MTB, HUMAN] })).toEqual([MTB, HUMAN]);
    expect(homeOrganismsFrom({ home_organism: MTB })).toEqual([MTB]);
    expect(homeOrganismsFrom({})).toEqual([]);
    expect(homeOrganismsFrom(undefined)).toEqual([]);
  });
});
