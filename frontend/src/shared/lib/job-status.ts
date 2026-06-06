/**
 * Terminal-status vocabulary for the import / bulk-registration async jobs
 * (CDD molecule + plate imports, bulk registration). These workflows report a
 * `status` string and reach one of three terminal states; the predicate is
 * centralized here so a backend rename/addition of a terminal status is a
 * one-line change instead of a hunt across every poll hook and status page.
 *
 * Distinct from `use-job-poll`'s SAR vocabulary (`ready`/`failed`/`cancelled`)
 * — the import workflows use `completed`/`completed_with_errors`/`failed`.
 */

/** Statuses at which an import / bulk-registration job has finished. */
export const TERMINAL_IMPORT_STATUSES = ["completed", "completed_with_errors", "failed"] as const;

export type TerminalImportStatus = (typeof TERMINAL_IMPORT_STATUSES)[number];

const TERMINAL_IMPORT_STATUS_SET: ReadonlySet<string> = new Set(TERMINAL_IMPORT_STATUSES);

/** True once an import / bulk-registration job has reached a terminal state. */
export function isTerminalImportStatus(status: string | null | undefined): boolean {
  return status != null && TERMINAL_IMPORT_STATUS_SET.has(status);
}
