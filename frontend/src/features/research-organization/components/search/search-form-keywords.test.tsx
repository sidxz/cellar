import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { SearchQuery } from "../../types";
import { SearchForm, decomposeQuery } from "./search-form";

vi.mock("../../hooks/use-search-count", () => ({ useSearchCount: () => ({ data: undefined }) }));
vi.mock("./project-filter", () => ({ ProjectFilter: () => <span>All projects</span> }));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => false);
  Element.prototype.releasePointerCapture = vi.fn();
});

function setup(initialQuery?: SearchQuery) {
  const onSearch = vi.fn();
  const props = {
    onSearch,
    onReset: vi.fn(),
    projectIds: [],
    onProjectsChange: vi.fn(),
    protocols: [],
    initialQuery,
  };
  return { ...render(<SearchForm {...props} />), onSearch, props };
}

describe("Keywords in the search form", () => {
  it("opens from the start card and submits pasted values immediately with Cmd+Enter", () => {
    const { onSearch } = setup();
    fireEvent.click(screen.getByRole("button", { name: /^Keywords/ }));
    expect(screen.getByRole("combobox", { name: "Keyword field" })).toHaveTextContent("Any field");
    fireEvent.change(screen.getByRole("textbox", { name: "Keyword values" }), {
      target: { value: "UCP1172, SDDC-1230\nTAMU-1585," },
    });
    expect(screen.getByText("3 values")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Keyword values" })).toHaveValue(
      "UCP1172, SDDC-1230\nTAMU-1585,",
    );
    fireEvent.keyDown(window, { key: "Enter", metaKey: true });
    expect(onSearch).toHaveBeenCalledWith(
      {
        logic: "and",
        criteria: [
          {
            type: "keyword_list",
            ref_type: "any",
            operator: "equals",
            values: ["UCP1172", "SDDC-1230", "TAMU-1585"],
          },
        ],
      },
      [],
    );
  });

  it("reads one typed term as contains until the chemist picks a match", () => {
    const { onSearch } = setup();
    fireEvent.click(screen.getByRole("button", { name: /^Keywords/ }));
    const box = screen.getByRole("textbox", { name: "Keyword values" });
    fireEvent.change(box, { target: { value: "kinostatin, CC-1" } });
    fireEvent.change(box, { target: { value: "kinostatin" } });
    fireEvent.click(screen.getByRole("button", { name: /^Search/ }));
    expect(onSearch.mock.calls[0][0].criteria[0]).toMatchObject({
      operator: "contains",
      values: ["kinostatin"],
    });
  });

  it("holds Search when a term has more than 1,000 values", () => {
    const { onSearch } = setup();
    fireEvent.click(screen.getByRole("button", { name: /^Keywords/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Keyword values" }), {
      target: { value: Array.from({ length: 1001 }, (_, i) => `V-${i}`).join("\n") },
    });
    expect(screen.getByText(/1,001 values · up to 1,000 per term/)).toBeInTheDocument();
    expect(screen.getByText("Keyword term 1 has more than 1,000 values")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Search/ })).toBeDisabled();
    fireEvent.keyDown(window, { key: "Enter", metaKey: true });
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("combines keyword rows with AND and keeps their fields and match operators", () => {
    const { onSearch } = setup();
    fireEvent.click(screen.getByRole("button", { name: /^Keywords/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Keyword values" }), {
      target: { value: "CC-1, CC-2" },
    });
    fireEvent.click(screen.getByRole("combobox", { name: "Keyword field" }));
    fireEvent.click(screen.getByRole("option", { name: "Compound ID" }));
    fireEvent.click(screen.getByRole("combobox", { name: "Keyword match" }));
    fireEvent.click(screen.getByRole("option", { name: "Equals" }));
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));
    fireEvent.change(screen.getAllByRole("textbox", { name: "Keyword values" })[1], {
      target: { value: "kinase" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Search/ }));
    expect(onSearch.mock.calls[0][0]).toEqual({
      logic: "and",
      criteria: [
        {
          type: "keyword_list",
          ref_type: "registration_number",
          operator: "equals",
          values: ["CC-1", "CC-2"],
        },
        { type: "keyword_list", ref_type: "any", operator: "contains", values: ["kinase"] },
      ],
    });
  });

  it("loads old text and bulk-list searches together and preserves their matching behavior", () => {
    const initialQuery: SearchQuery = {
      criteria: [
        { type: "text", field: "name", operator: "contains", value: "1,2-dichlorobenzene" },
        { type: "keyword_list", ref_type: "external_id", values: ["V-1", "V-2"], negate: true },
      ],
      logic: "and",
    };
    const { onSearch } = setup(initialQuery);
    const keywords = screen.getByRole("region", { name: "Keywords" });
    expect(within(keywords).getAllByRole("textbox")).toHaveLength(2);
    expect(screen.queryByRole("region", { name: "Advanced" })).not.toBeInTheDocument();
    expect(
      within(keywords).getAllByRole("combobox", { name: "Keyword match" })[1],
    ).toHaveTextContent("Equals");
    expect(screen.getByText("Exclude matches")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Search/ }));
    expect(onSearch).toHaveBeenCalledWith(initialQuery, []);
    expect(decomposeQuery(initialQuery).keywordCriteria).toEqual(initialQuery.criteria);
  });

  it("loads replacement saved values, removes rows, and skips empty input", () => {
    const { rerender, props, onSearch } = setup({
      criteria: [{ type: "keyword_list", ref_type: "name", values: ["A,B"] }],
    });
    rerender(
      <SearchForm
        {...props}
        initialQuery={{
          criteria: [{ type: "keyword_list", ref_type: "name", values: ["A", "B"] }],
        }}
      />,
    );
    expect(screen.getByRole("textbox", { name: "Keyword values" })).toHaveValue("A\nB");
    fireEvent.change(screen.getByRole("textbox", { name: "Keyword values" }), {
      target: { value: ", \n ," },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Search/ }));
    expect(onSearch).toHaveBeenCalledWith({ criteria: [], logic: "and" }, []);
    fireEvent.click(screen.getByRole("button", { name: "Remove keyword condition" }));
    expect(screen.queryByRole("textbox", { name: "Keyword values" })).not.toBeInTheDocument();
  });
});
