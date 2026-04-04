import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Edge middleware — lightweight request processing.
 *
 * Auth tokens live in localStorage (AuthZ mode), so edge middleware
 * cannot validate them (browser page navigations don't include custom
 * HTTP headers). Route protection is handled client-side via AuthzGuard
 * in the dashboard layout.
 *
 * Once @sentinel-auth/nextjs supports HttpOnly cookie storage (BFF pattern),
 * this can be upgraded to createSentinelAuthzMiddleware for server-side
 * token validation. See: https://github.com/sidxz/Sentinel/issues/14
 */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Forward workspace info if available (read by Server Components via headers())
  const url = request.nextUrl;
  if (url.pathname !== "/login" && url.pathname !== "/auth/callback") {
    response.headers.set("x-request-pathname", url.pathname);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next|api|favicon\\.ico|.*\\..*).*)"],
};
