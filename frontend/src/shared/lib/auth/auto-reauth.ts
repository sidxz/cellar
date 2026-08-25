/**
 * Whether the AuthzProvider's silent (`prompt=none`) re-auth should be enabled
 * for the given route.
 *
 * autoReauth must NOT run on the auth-flow routes: on `/auth/callback` it would
 * preempt the OAuth response the callback exists to process, and on `/login` it
 * would hijack an interactive sign-in. (A stale-but-valid authz token keeps the
 * SDK in the `needs_reauth` state on every route, and an interactive login sets
 * no silent-in-flight marker to guard against it.) It belongs only on the app's
 * protected routes, where a reloaded session should re-auth seamlessly — and the
 * kiosk page runs with no user session at all — a device token, not a person —
 * so silent re-auth must never fire there.
 */
const NO_AUTO_REAUTH_PREFIXES = ["/login", "/auth", "/kiosk"];

export function shouldAutoReauth(pathname: string | null): boolean {
  if (!pathname) return false;
  return !NO_AUTO_REAUTH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}
