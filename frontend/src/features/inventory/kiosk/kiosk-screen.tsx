"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { formatDate } from "@/shared/lib/format-date";
import { useCallback, useEffect, useRef, useState } from "react";
import { kioskConfirm, kioskScan, readKioskToken, writeKioskToken } from "./kiosk-api";

type Result =
  | {
      kind: "ok";
      action: "checkout" | "return";
      plateLabel: string;
      borrower: string | null;
      due: string | null;
    }
  | { kind: "error"; message: string };

const OK_MS = 3000;
const ERROR_MS = 5000;

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return "Plate not recognized for this device's organization";
    // Cellar's DomainError handler serializes `{ error, message }`; only
    // FastAPI's own validation errors use `{ detail }`. Check both.
    const b = err.body as { message?: unknown; detail?: unknown } | undefined;
    const text =
      typeof b?.message === "string"
        ? b.message
        : typeof b?.detail === "string"
          ? b.detail
          : undefined;
    if (text) return text;
  }
  return "Scan failed — try again";
}

export default function KioskScreen() {
  const [token, setToken] = useState<string | null>(() =>
    typeof window === "undefined" ? null : readKioskToken(),
  );
  const [tokenDraft, setTokenDraft] = useState("");
  const [barcode, setBarcode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const focusInput = useCallback(() => inputRef.current?.focus(), []);

  useEffect(() => {
    if (token) focusInput();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [token, focusInput]);

  const showResult = (r: Result) => {
    if (timer.current) clearTimeout(timer.current);
    setResult(r);
    timer.current = setTimeout(
      () => {
        setResult(null);
        focusInput();
      },
      r.kind === "ok" ? OK_MS : ERROR_MS,
    );
  };

  const saveToken = () => {
    const t = tokenDraft.trim();
    if (!t) return;
    writeKioskToken(t);
    setToken(t);
    setTokenDraft("");
  };

  const forgetToken = () => {
    writeKioskToken(null);
    setToken(null);
    setResult(null);
  };

  const scan = async () => {
    const code = barcode.trim();
    if (!token || !code || busy) return;
    setBusy(true);
    setBarcode("");
    try {
      const hit = await kioskScan(token, code);
      const done = await kioskConfirm(token, { loan_id: hit.loan_id, item_id: hit.item_id });
      showResult({
        kind: "ok",
        action: done.new_status === "checked_out" ? "checkout" : "return",
        plateLabel: hit.plate_label,
        borrower: hit.borrower_org_name,
        due: hit.due_date,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        forgetToken();
        return;
      }
      showResult({ kind: "error", message: errorMessage(err) });
    } finally {
      setBusy(false);
      focusInput();
    }
  };

  if (!token) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8 text-foreground">
        <h1 className="text-2xl font-semibold">Kiosk setup</h1>
        <p className="max-w-md text-center text-sm text-muted-foreground">
          Paste the device token issued under Admin → Kiosk Devices. It is stored only in this
          browser.
        </p>
        <form
          className="flex w-full max-w-md gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            saveToken();
          }}
        >
          <Input
            type="password"
            aria-label="Device token"
            autoComplete="off"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
          />
          <Button type="submit" disabled={!tokenDraft.trim()}>
            Save
          </Button>
        </form>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background p-8 text-foreground">
      <h1 className="text-4xl font-semibold">Ready to scan</h1>
      <form
        className="w-full max-w-lg"
        onSubmit={(e) => {
          e.preventDefault();
          void scan();
        }}
      >
        <Input
          ref={inputRef}
          aria-label="Barcode"
          autoComplete="off"
          autoFocus
          disabled={busy}
          value={barcode}
          onChange={(e) => setBarcode(e.target.value)}
          className="h-16 text-center font-mono text-3xl"
          placeholder="Scan a plate barcode"
        />
      </form>
      {result ? (
        <output
          aria-live="polite"
          data-testid="kiosk-result"
          className={`w-full max-w-lg rounded-xl p-8 text-center text-white ${result.kind === "ok" ? "bg-green-600" : "bg-red-600"}`}
        >
          {result.kind === "ok" ? (
            <>
              <p className="text-3xl font-bold">
                {result.action === "checkout" ? "Checked out" : "Checked in"}
              </p>
              <p className="mt-2 text-xl">{result.plateLabel}</p>
              {result.borrower ? <p className="mt-1 text-lg">{result.borrower}</p> : null}
              {result.due ? (
                <p className="mt-1 text-sm opacity-90">due {formatDate(result.due)}</p>
              ) : null}
            </>
          ) : (
            <p className="text-2xl font-semibold">{result.message}</p>
          )}
        </output>
      ) : null}
      <button
        type="button"
        onClick={forgetToken}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        Change device
      </button>
    </main>
  );
}
