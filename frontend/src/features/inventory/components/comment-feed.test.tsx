import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { CommentFeed } from "./comment-feed";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

const comments = [
  {
    id: "c1",
    target_type: "plate",
    target_id: "p1",
    body: "second",
    author_name: "Jane Doe",
    created_at: "2026-08-25T12:00:00Z",
  },
  {
    id: "c2",
    target_type: "plate",
    target_id: "p1",
    body: "first",
    author_name: "Jane Doe",
    created_at: "2026-08-24T12:00:00Z",
  },
];

function setup(props: Partial<Parameters<typeof CommentFeed>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <CommentFeed scope={{ targetType: "plate", targetId: "p1" }} canWrite={false} {...props} />,
    { wrapper },
  );
}

describe("CommentFeed", () => {
  it("lists comments newest first with author and body", async () => {
    mocked.mockImplementation(async () => comments);
    setup();
    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(screen.getAllByText("Jane Doe")).toHaveLength(2);
    const bodies = screen.getAllByText(/^(second|first)$/).map((el) => el.textContent);
    expect(bodies).toEqual(["second", "first"]);
  });

  it("hides the composer when canWrite is false", async () => {
    mocked.mockImplementation(async () => comments);
    setup({ canWrite: false });
    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add comment/i })).not.toBeInTheDocument();
  });

  it("posts a new comment and clears the textarea when canWrite is true", async () => {
    mocked.mockImplementation(async (opts: { method: string }) => {
      if (opts.method === "POST") return comments[0];
      return comments;
    });
    setup({ canWrite: true });
    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "a new note" } });
    fireEvent.click(screen.getByRole("button", { name: /add comment/i }));

    await waitFor(() => {
      const postCall = mocked.mock.calls.find(
        (c) => (c[0] as { method: string }).method === "POST",
      );
      expect(postCall).toBeTruthy();
      expect(postCall?.[0]).toMatchObject({
        url: "/api/v1/comments",
        method: "POST",
        data: { target_type: "plate", target_id: "p1", body: "a new note" },
      });
    });
    await waitFor(() => expect(textarea.value).toBe(""));
  });
});

describe("CommentFeed loan-context link (I2)", () => {
  const commentWithLoan = [
    {
      id: "c3",
      target_type: "plate_group",
      target_id: "g1",
      body: "0.5 uL for NadE",
      author_name: "Jane Doe",
      created_at: "2026-08-25T12:00:00Z",
      loan_id: "loan-1",
    },
  ];

  it("shows the 'in loan' link when the feed's own scope is not that loan", async () => {
    mocked.mockImplementation(async () => commentWithLoan);
    setup({ scope: { targetType: "plate_group", targetId: "g1" } });
    await waitFor(() => expect(screen.getByText("0.5 uL for NadE")).toBeInTheDocument());
    const link = screen.getByRole("link", { name: "in loan" });
    expect(link).toHaveAttribute("href", "/inventory/loans#all");
  });

  it("hides the link when the entry is shown on that loan's own feed", async () => {
    mocked.mockImplementation(async () => commentWithLoan);
    setup({ scope: { loanId: "loan-1" } });
    await waitFor(() => expect(screen.getByText("0.5 uL for NadE")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "in loan" })).not.toBeInTheDocument();
  });
});
