"use client";

import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import {
  type CddMoleculeIdentifierCheck,
  useCheckCddMoleculeIdentifiers,
} from "../hooks/use-cdd-molecule-import";

const plural = (count: number, noun: string) =>
  `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;

/**
 * The list for the "Specific molecules" import mode: the pasted identifiers and
 * the check that says which of them the vault knows. It imports nothing; the
 * page's Start Import button does, from the answer handed over by `onChecked`.
 *
 * The pasted text goes to the check as it is. The server alone splits it into
 * identifiers, so this component shows only what the check returns.
 */
export function SelectedMoleculesImport({
  text,
  onTextChange,
  checked,
  onChecked,
}: {
  /** The pasted list. The page holds it, so it outlives a switch of import mode. */
  text: string;
  onTextChange: (text: string) => void;
  /** The check's answer for the list as it stands, or null when it has none. */
  checked: CddMoleculeIdentifierCheck | null;
  /** A check came back: the text it was asked about, and its answer. */
  onChecked: (text: string, result: CddMoleculeIdentifierCheck) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const check = useCheckCddMoleculeIdentifiers();

  const handleCheck = async () => {
    setError(null);
    try {
      onChecked(text, await check.mutateAsync(text));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not check the identifiers");
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        <Label htmlFor="molecule-identifiers">Identifiers</Label>
        <Textarea
          id="molecule-identifiers"
          rows={5}
          className="max-h-64 font-mono"
          placeholder={"CMPD-0001\nCMPD-0002"}
          value={text}
          // Locked while a check is out, so its answer is always for the list shown.
          disabled={check.isPending}
          onChange={(e) => onTextChange(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          One per line, or separated by commas. Repeats are ignored.
        </p>
      </div>

      <Button
        variant="outline"
        onClick={handleCheck}
        disabled={text.trim() === "" || check.isPending}
      >
        {check.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        Check identifiers
      </Button>

      {error && (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
      )}

      {checked && (
        <div className="space-y-3 rounded-md border p-4 text-sm">
          <p>
            {checked.found.length.toLocaleString()} of{" "}
            {plural(checked.found.length + checked.not_found.length, "identifier")} found in CDD
            Vault.
          </p>

          <NotFoundIdentifiers
            title={`Not found (${checked.not_found.length.toLocaleString()})`}
            identifiers={checked.not_found}
          />
        </div>
      )}
    </div>
  );
}

/** The identifiers the vault did not know, as a short scrolling list. Nothing when there are none. */
export function NotFoundIdentifiers({
  title,
  identifiers,
}: {
  title: string;
  identifiers: string[];
}) {
  if (identifiers.length === 0) return null;
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">{title}</p>
      <ul className="max-h-40 overflow-y-auto font-mono text-xs text-muted-foreground">
        {identifiers.map((identifier) => (
          <li key={identifier}>{identifier}</li>
        ))}
      </ul>
    </div>
  );
}
