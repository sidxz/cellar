export const IMPORT_SCOPES = [
  {
    value: "full_vault",
    label: "All molecules",
    description: "Read the entire vault and match existing ChemCellar records.",
  },
  {
    value: "sync",
    label: "New and changed molecules",
    description: "Read molecules modified since the saved sync timestamp.",
  },
  {
    value: "filtered",
    label: "Selected molecules",
    description: "Find molecules by their CDD names or synonyms.",
  },
] as const;

export type ImportMode = (typeof IMPORT_SCOPES)[number]["value"];

export function importScopeLabel(mode: string) {
  return (
    IMPORT_SCOPES.find((scope) => scope.value === mode)?.label ??
    (mode === "full" ? "All molecules" : "Unknown scope")
  );
}

export function importOutcome(status: string, reason?: string | null, errors = 0) {
  if (status === "failed" && /^cancelled by user$|^canceled by user$/i.test(reason ?? "")) {
    return { label: "Stopped by user", tone: "secondary", kind: "stopped" } as const;
  }
  if (status === "failed") {
    return { label: "Import failed", tone: "destructive", kind: "failed" } as const;
  }
  if (status === "completed_with_errors" || (status === "completed" && errors > 0)) {
    return { label: "Finished with errors", tone: "warning", kind: "partial" } as const;
  }
  if (status === "completed") {
    return { label: "Completed", tone: "success", kind: "success" } as const;
  }
  const label = {
    pending: "Starting",
    discovering: "Reading vault",
    exporting: "Preparing export",
    processing: "Importing",
  }[status];
  return { label: label ?? "In progress", tone: "outline", kind: "active" } as const;
}

/** Short explanations for known diagnostics; the original is always available in the report. */
export function describeImportIssue(line: string) {
  const separator = line.indexOf(": ");
  const name = separator > 0 ? line.slice(0, separator) : "Import issue";
  const reason = separator > 0 ? line.slice(separator + 2) : line;
  if (/invalid smiles|failed to parse smiles/i.test(reason)) {
    return {
      name,
      reason: "Structure could not be read",
      next: "Review the structure in CDD Vault before retrying.",
    };
  }
  if (/standardization failed|failed to generate inchikey/i.test(reason)) {
    return {
      name,
      reason: "Structure could not be standardized",
      next: "Review the structure in CDD Vault before retrying.",
    };
  }
  if (/already.*(assigned|ID of)/i.test(reason)) {
    return {
      name,
      reason: "Identifier is already assigned",
      next: "Review the existing compound and identifier mapping.",
    };
  }
  if (/not stored|skipped/i.test(reason)) {
    return {
      name,
      reason: "A source value was not saved",
      next: "Review the source value and field mapping.",
    };
  }
  return { name, reason, next: "Review the source record and field mapping." };
}
