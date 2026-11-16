import { ApiError } from "@/shared/lib/api/custom-instance";

/** The server's own sentence when it sent one (`{message}`), else the error text. */
export function errorText(error: unknown): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  if (typeof body?.message === "string") return body.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}
