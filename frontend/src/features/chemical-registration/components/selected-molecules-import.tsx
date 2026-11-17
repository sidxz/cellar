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
 * Import a pasted list of vault molecules: check which identifiers the vault
 * knows, then import the found ones. Nothing is imported until Import is pressed.
 *
 * The pasted text goes to the check as it is. The server alone splits it into
 * identifiers, so this component shows only what the check returns.
 */
export function SelectedMoleculesImport({
  organizationSelected,
  isImporting,
  onImport,
}: {
  organizationSelected: boolean;
  isImporting: boolean;
  onImport: (found: string[], notFound: string[]) => void;
}) {
  const [text, setText] = useState("");
  // The answer for the list as it stands; cleared whenever the list is edited.
  const [checked, setChecked] = useState<CddMoleculeIdentifierCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const check = useCheckCddMoleculeIdentifiers();

  const handleCheck = async () => {
    setError(null);
    try {
      setChecked(await check.mutateAsync(text));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not check the identifiers");
    }
  };

  return (
    <section aria-labelledby="selected-molecules-heading" className="max-w-lg space-y-4">
      <div className="space-y-1">
        <h3 id="selected-molecules-heading" className="text-sm font-semibold">
          Import specific molecules
        </h3>
        <p className="text-sm text-muted-foreground">
          Paste the identifiers of the molecules you need: the name or a synonym each one has in CDD
          Vault. Only those molecules and their batches are imported, for the organization selected
          above.
        </p>
      </div>

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
          onChange={(e) => {
            setText(e.target.value);
            setChecked(null);
          }}
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

          <div className="flex items-center gap-3">
            <Button
              onClick={() => onImport(checked.found, checked.not_found)}
              disabled={checked.found.length === 0 || !organizationSelected || isImporting}
            >
              {isImporting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Import
            </Button>
            <span className="tabular-nums text-muted-foreground">
              {checked.found.length.toLocaleString()} found
            </span>
          </div>
          {!organizationSelected && checked.found.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Select the originating organization above to import.
            </p>
          )}
        </div>
      )}
    </section>
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
