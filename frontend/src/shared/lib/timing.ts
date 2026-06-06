/** Standard delays for ephemeral UI feedback. Centralized so visual cadence
 * stays consistent across copy buttons, success toasts, and auto-close
 * dialogs. */

/** How long a "Copied!" indicator stays visible before reverting. */
export const COPY_FEEDBACK_MS = 1500;

/** How long a success dialog lingers before auto-closing. */
export const SUCCESS_DIALOG_AUTOCLOSE_MS = 1500;

// ---------------------------------------------------------------------------
// Async-job poll cadence
//
// Shared cadence for the "start returns a job id, then poll a /status endpoint
// until terminal" pattern. Centralized so the long-poll hooks don't each carry
// their own bare `return 2000;` literal that drifts as new poll hooks get
// copy-pasted.
// ---------------------------------------------------------------------------

/** Default poll interval for an active async job (bulk registration, imports). */
export const JOB_POLL_INTERVAL_MS = 2000;

/** Slower poll interval for heavier/longer-running jobs (e.g. bulk reg wizard). */
export const JOB_POLL_SLOW_INTERVAL_MS = 3000;

/** Number of poll attempts before the backoff doubles the interval. */
export const JOB_POLL_BACKOFF_AFTER = 3;

/**
 * Poll interval with a simple step backoff: the base interval for the first
 * {@link JOB_POLL_BACKOFF_AFTER} attempts, then double it. `attempt` is the
 * count of completed polls (0-based).
 */
export function jobPollBackoffMs(attempt: number, baseMs = JOB_POLL_INTERVAL_MS): number {
  return attempt < JOB_POLL_BACKOFF_AFTER ? baseMs : baseMs * 2;
}
