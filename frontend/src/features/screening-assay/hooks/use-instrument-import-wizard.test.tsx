import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InstrumentImportResult, InstrumentPreview } from "../types";

// No signed-in client in tests: requests carry no auth headers.
vi.mock("@/shared/lib/auth/config", () => ({ getDuarClient: () => null }));

import { useInstrumentImportWizard } from "./use-instrument-import-wizard";

const preview: InstrumentPreview = {
  reader: "reader-1",
  reader_label: "Reader one raw export",
  holder: { kind: "cassette", rows: 1, columns: 2, label: "Holder of 2 positions" },
  dose_unit: "uM",
  positions: [
    { row: 1, column: 1, position_label: "Position 1", label: "ABC-0000001", suggestion: null },
    { row: 1, column: 2, position_label: "Position 2", label: "", suggestion: null },
  ],
  channels: [{ key: "a", label: "Channel A", x_unit: "°C", y_unit: null, x_label: null }],
  series: [],
  readouts: [],
  settings: {},
  warnings: [],
};

const result: InstrumentImportResult = {
  reader: "reader-1",
  positions_created: 2,
  curves_created: 2,
  values_inserted: 0,
  warnings: [],
  compute_warning: null,
  file_attached: true,
  attachment_id: "att-1",
  attachment_warning: null,
  stored_file_name: null,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderWizardHook() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const onOpenChange = vi.fn();
  const hook = renderHook(() => useInstrumentImportWizard({ runId: "run-1", onOpenChange }), {
    wrapper,
  });
  return { ...hook, onOpenChange };
}

const file = new File(["bytes"], "export.bin");

describe("useInstrumentImportWizard", () => {
  it("previews the chosen file, takes an edit and imports it", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith("/preview-instrument-file") ? json(preview) : json(result, 201),
    );
    const { result: hook } = renderWizardHook();

    act(() => hook.current.handleFile(file));
    await waitFor(() => expect(hook.current.preview).toEqual(preview));
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/v1\/runs\/run-1\/preview-instrument-file$/);
    expect(hook.current.draft.positions.map((p) => p.positionLabel)).toEqual([
      "Position 1",
      "Position 2",
    ]);
    expect(hook.current.canImport).toBe(true);

    act(() => hook.current.updatePosition("1:2", { label: "protein alone", dose: "abc" }));
    expect(hook.current.canImport).toBe(false);
    act(() => hook.current.updatePosition("1:2", { dose: "5" }));
    expect(hook.current.canImport).toBe(true);

    act(() => hook.current.handleImport());
    await waitFor(() => expect(hook.current.result).toEqual(result));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toMatch(/\/api\/v1\/runs\/run-1\/import-instrument-file$/);
    const body = init.body as FormData;
    expect(body.get("file")).toBeInstanceOf(File);
    const labelling = JSON.parse(body.get("labelling") as string);
    expect(labelling.positions[1]).toMatchObject({
      row: 1,
      column: 2,
      used: true,
      label: "protein alone",
      dose: 5,
    });
    expect(hook.current.error).toBeNull();
  });

  it("shows the API's own words when the preview is refused", async () => {
    fetchMock.mockResolvedValue(
      json({ detail: "Unrecognized instrument file. Supported formats: Reader one" }, 422),
    );
    const { result: hook } = renderWizardHook();

    act(() => hook.current.handleFile(file));
    await waitFor(() =>
      expect(hook.current.error).toBe(
        "Unrecognized instrument file. Supported formats: Reader one",
      ),
    );
    expect(hook.current.preview).toBeNull();
    expect(hook.current.canImport).toBe(false);
  });

  it("starts over when the dialog closes", async () => {
    fetchMock.mockResolvedValue(json(preview));
    const { result: hook, onOpenChange } = renderWizardHook();

    act(() => hook.current.handleFile(file));
    await waitFor(() => expect(hook.current.preview).not.toBeNull());
    act(() => hook.current.setStep(3));

    act(() => hook.current.handleOpenChange(false));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(hook.current).toMatchObject({
      step: 1,
      file: null,
      preview: null,
      result: null,
      error: null,
      draft: { positions: [], readoutBySeries: {} },
    });
  });
});
