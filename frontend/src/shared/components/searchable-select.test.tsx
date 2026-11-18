import { Dialog, DialogContent, DialogTitle } from "@/shared/components/ui/dialog";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { SearchableSelect } from "./searchable-select";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
});

const options = Array.from({ length: 40 }, (_, i) => ({ value: `v${i}`, label: `Option ${i}` }));

/** Opens the picker and gives its list real scroll metrics (jsdom lays nothing out). */
function openScrollableList() {
  fireEvent.click(screen.getByRole("combobox"));
  const list = document.querySelector<HTMLElement>("[data-slot='command-list']");
  if (!list) throw new Error("the picker list did not open");
  list.style.overflowY = "auto";
  Object.defineProperty(list, "scrollHeight", { value: 1200 });
  Object.defineProperty(list, "clientHeight", { value: 300 });
  return list;
}

describe("SearchableSelect", () => {
  it("scrolls with the wheel when it is opened inside a dialog", () => {
    render(
      <Dialog open>
        <DialogContent aria-describedby={undefined}>
          <DialogTitle>New Protocol</DialogTitle>
          <SearchableSelect options={options} value={null} onValueChange={vi.fn()} />
        </DialogContent>
      </Dialog>,
    );
    const list = openScrollableList();

    // The dialog's scroll lock cancels a wheel it believes is outside the dialog.
    const wheel = new WheelEvent("wheel", { deltaY: 100, bubbles: true, cancelable: true });
    (list.querySelector("[data-slot='command-item']") as HTMLElement).dispatchEvent(wheel);

    expect(wheel.defaultPrevented).toBe(false);
  });

  it("leaves the page scrollable when it is opened outside a dialog", () => {
    render(<SearchableSelect options={options} value={null} onValueChange={vi.fn()} />);
    openScrollableList();
    expect(document.body).not.toHaveAttribute("data-scroll-locked");
  });
});
