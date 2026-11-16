import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { WorkbenchProvider } from "../store/workbench-context";
import { WorkbenchBody } from "./workbench-body";

const show = (editor?: ReactNode) =>
  render(
    <WorkbenchProvider initialPanels={[]}>
      <WorkbenchBody
        plots={<p>plots</p>}
        table={<p>table</p>}
        rail={<input aria-label="Rail field" />}
        editor={editor}
      />
    </WorkbenchProvider>,
  );

describe("WorkbenchBody", () => {
  it("moves focus into the filters overlay, and Escape returns it to the tab", () => {
    show();
    const tab = screen.getByRole("button", { name: "Filters (0)" });
    tab.focus();
    fireEvent.click(tab);
    expect(tab).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close filters" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Rail field" }), { key: "Escape" });
    expect(tab).toHaveAttribute("aria-expanded", "false");
    expect(tab).toHaveFocus();
  });

  it("returns focus to the tab when the overlay's close button is used", () => {
    show();
    const tab = screen.getByRole("button", { name: "Filters (0)" });
    fireEvent.click(tab);
    fireEvent.click(screen.getByRole("button", { name: "Close filters" }));
    expect(tab).toHaveFocus();
  });

  it("stacks the plots over the table in the page flow, with the rail sticky beside them", () => {
    const { container } = show();
    // No split to drag and no inner scroll box: the page itself scrolls.
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    expect(screen.getByText("plots").compareDocumentPosition(screen.getByText("table"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.getByText("plots").closest(".overflow-auto")).toBeNull();
    expect(screen.getByText("table").closest(".overflow-auto")).toBeNull();
    expect(screen.getByRole("complementary", { name: "Filters" })).toHaveClass("xl:sticky");
    // The dashboard's <main> scrolls nothing; the viewport does, so sticky parts stick.
    expect(container.querySelector("style")?.textContent).toContain(
      "main:has(.viz-workbench){overflow:visible}",
    );
  });

  it("keeps the plot editor beside the page, sticky, as tall as its content up to the viewport", () => {
    show(<p>editor</p>);
    const editor = screen.getByRole("complementary", { name: "Edit plot" });
    expect(editor).toHaveClass("sticky", "max-h-[calc(100dvh-1rem)]", "flex-col");
    // A fixed height would stretch a short page to the viewport and scroll for nothing.
    expect(editor).not.toHaveClass("h-[calc(100dvh-1rem)]");
  });
});
