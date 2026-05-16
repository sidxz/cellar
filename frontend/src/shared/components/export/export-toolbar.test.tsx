import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExportToolbar } from "./export-toolbar";

// Radix DropdownMenu renders into a portal that is unreliable under jsdom.
// Mock the four shadcn DropdownMenu primitives so their children render
// inline — the portal and pointer-event machinery is irrelevant to the
// intent of this test (verifying the four format items are wired up).
vi.mock("@/shared/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: () => void;
  }) => <button onClick={onSelect}>{children}</button>,
}));

vi.mock("./use-export", () => ({
  useExport: () => ({
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    job: null,
    isPending: false,
    error: null,
  }),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("ExportToolbar", () => {
  it("renders four format options", () => {
    render(<ExportToolbar buildRequest={() => null} />, { wrapper });
    expect(screen.getByText("Excel")).toBeTruthy();
    expect(screen.getByText("CSV")).toBeTruthy();
    expect(screen.getByText("SDF")).toBeTruthy();
    expect(screen.getByText("PDF")).toBeTruthy();
  });
});
