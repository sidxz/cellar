import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/shared/lib/api/custom-instance";
import type { ResultNoteHistoryResponse } from "@/shared/lib/api/model";

import type { CampaignResultResponse } from "../../types";
import { NotesPopover } from "./notes-popover";

const mutate = vi.fn();
const hook = vi.hoisted(() => ({
  options: undefined as
    | { mutation?: { onSuccess?: () => void; onError?: (err: unknown) => void } }
    | undefined,
  history: { versions: [] } as ResultNoteHistoryResponse,
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch: (options: typeof hook.options) => {
    hook.options = options;
    return { mutate, isPending: false };
  },
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string | null | undefined) => (id === "u-2" ? "Grace" : "Ada"),
}));
vi.mock("../../hooks/use-campaigns", () => ({
  campaignKeys: {
    detail: (id: string) => ["campaigns", id],
    noteHistory: (id: string, rid: string) => ["campaigns", id, "results", rid, "note-history"],
  },
  useResultNoteHistory: () => ({ data: hook.history, isLoading: false }),
}));

function row(notes: string | null): CampaignResultResponse {
  return {
    id: "r-1",
    molecule_id: "mol-1",
    notes,
    notes_edited_by: notes ? "u-1" : null,
    notes_edited_at: notes ? "2026-11-01T09:00:00Z" : null,
    measurements: [],
    stage_outcomes: [],
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function open(notes: string | null, readOnly = false) {
  return render(
    <NotesPopover campaignId="c-1" result={row(notes)} onClose={() => {}} readOnly={readOnly} />,
    { wrapper },
  );
}

function type(text: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
}

beforeEach(() => {
  mutate.mockReset();
  hook.history = { versions: [] };
});

describe("NotesPopover", () => {
  it("saves with the note as it was opened", () => {
    open("old");
    type("new");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c-1",
      resultId: "r-1",
      data: { notes: "new", expected_notes: "old" },
    });
  });

  it("a first note is saved as based on no note", () => {
    open(null);
    type("  Watch hERG ");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate.mock.calls[0][0].data).toEqual({ notes: "Watch hERG", expected_notes: null });
  });

  it("a stale save shows their note and keeps your text", () => {
    open("old");
    type("mine");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    act(() =>
      hook.options?.mutation?.onError?.(
        new ApiError("API error: 409", 409, {
          error: "StaleEditError",
          message: "Someone changed this note since you opened it. Your text was not saved.",
          current: {
            notes: "theirs",
            notes_edited_by: "u-2",
            notes_edited_at: "2026-11-21T10:00:00+00:00",
          },
        }),
      ),
    );

    expect(screen.getByText("Someone changed this note since you opened it")).toBeInTheDocument();
    expect(screen.getByText("theirs")).toBeInTheDocument();
    expect(screen.getByText(/^by Grace · /)).toBeInTheDocument();
    expect(screen.getByText("Save again to replace it with yours.")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("mine");

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mutate.mock.calls[1][0].data).toEqual({ notes: "mine", expected_notes: "theirs" });
  });

  it("a stale save on a note they removed says so", () => {
    open("old");
    type("mine");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    act(() =>
      hook.options?.mutation?.onError?.(
        new ApiError("API error: 409", 409, {
          error: "StaleEditError",
          current: { notes: null, notes_edited_by: "u-2", notes_edited_at: "2026-11-21T10:00:00Z" },
        }),
      ),
    );
    expect(screen.getByText("Note removed")).toBeInTheDocument();
  });

  it("history lists versions newest first", () => {
    hook.history = {
      versions: [
        { notes: "current text", edited_by: "u-2", edited_at: "2026-11-21T10:00:00Z" },
        { notes: null, edited_by: "u-1", edited_at: "2026-11-10T10:00:00Z" },
        { notes: "the first note", edited_by: null, edited_at: null },
      ],
    };
    open("current text");
    fireEvent.click(screen.getByRole("button", { name: "History" }));

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("current text");
    expect(items[0]).toHaveTextContent(/by Grace · /);
    expect(items[1]).toHaveTextContent("Note removed");
    expect(items[1]).toHaveTextContent(/by Ada · /);
    expect(items[2]).toHaveTextContent("the first note");
    expect(items[2]).toHaveTextContent("Before edits were tracked");
  });

  it("an empty history says there is nothing earlier", () => {
    open(null);
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(screen.getByText("No earlier versions.")).toBeInTheDocument();
  });

  it("read-only shows the note and its history without a textarea", () => {
    open("Watch hERG", true);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.getByText("Watch hERG")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "History" })).toBeInTheDocument();
  });
});
