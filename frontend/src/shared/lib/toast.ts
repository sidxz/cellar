import { type ExternalToast, toast } from "sonner";

/**
 * Thin wrappers over sonner so feature code never imports `toast` directly.
 * Centralising the toast surface keeps copy/duration/id conventions in one
 * place and lets us swap the toast implementation without a feature-wide edit.
 */

/** A stable toast id — pass the same id to update/dismiss an existing toast. */
export type ToastId = string | number;

export function showSuccess(message: string, opts?: ExternalToast): ToastId {
  return toast.success(message, opts);
}

export function showError(message: string, opts?: ExternalToast): ToastId {
  return toast.error(message, opts);
}

export function showInfo(message: string, opts?: ExternalToast): ToastId {
  return toast.info(message, opts);
}

export function showWarning(message: string, opts?: ExternalToast): ToastId {
  return toast.warning(message, opts);
}

/**
 * A loading/progress toast. Pass a stable `id` to keep updating the same toast
 * (e.g. flip it to success on completion) and to dismiss it later with that id.
 * Returns the toast id sonner assigned.
 */
export function showLoading(message: string, opts?: ExternalToast): ToastId {
  return toast.loading(message, opts);
}

/**
 * A neutral message toast (no status colour/icon). Use for informational
 * summaries that carry their own description/duration rather than a status.
 */
export function showMessage(message: string, opts?: ExternalToast): ToastId {
  return toast.message(message, opts);
}

/** Dismiss a toast by id (or all toasts when called with no id). */
export function dismissToast(id?: ToastId): void {
  toast.dismiss(id);
}
