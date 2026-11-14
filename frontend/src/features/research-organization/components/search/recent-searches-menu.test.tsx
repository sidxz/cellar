import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { RecentSearch } from "../../hooks/use-recent-searches";
import { RecentSearchesMenu, storedCriteria } from "./recent-searches-menu";

const clear = vi.fn();
const assay = (protocol_id: string) => ({ type: "activity", protocol_id, where: [] });
const searches: RecentSearch[] = [
  {
    id: "r1",
    query: { logic: "and", criteria: [assay("p1")], aggregation: "latest_run" },
    columns: { protocolColumns: [] },
    result_count: 27,
    ran_at: new Date().toISOString(),
  },
  {
    id: "r2",
    query: { logic: "and", criteria: [assay("p2")], aggregation: "latest_run" },
    columns: null,
    result_count: 1,
    ran_at: new Date().toISOString(),
  },
];

vi.mock("../../hooks/use-recent-searches", () => ({
  useRecentSearches: () => ({ data: searches, isLoading: false }),
  useClearRecentSearches: () => ({ mutate: clear, isPending: false }),
}));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => false);
});

const context = {
  protocols: [
    { id: "p1", name: "HsaA/B binding" },
    { id: "p2", name: "Resazurin" },
  ],
} as never;

function open(onPick = vi.fn()) {
  render(
    <RecentSearchesMenu
      currentQuery={storedCriteria(searches[0].query)}
      summaryContext={context}
      onPick={onPick}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /Recent searches/ }));
  return onPick;
}

describe("<RecentSearchesMenu />", () => {
  it("lists each search with its count, and marks the one on screen", () => {
    open();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("HsaA/B binding");
    expect(rows[0]).toHaveTextContent("27 compounds");
    expect(rows[0]).toHaveTextContent("on screen");
    expect(rows[1]).toHaveTextContent("1 compound ·");
    expect(rows[1]).not.toHaveTextContent("on screen");
  });

  it("hands the picked search back to run it", () => {
    const onPick = open();
    fireEvent.click(screen.getByRole("button", { name: /Resazurin/ }));
    expect(onPick).toHaveBeenCalledWith(searches[1]);
  });

  it("clears the history", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
    expect(clear).toHaveBeenCalled();
  });
});
