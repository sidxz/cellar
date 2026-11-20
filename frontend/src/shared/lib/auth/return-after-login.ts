// The page a signed-out visitor asked for, so sign-in can return there (a deep link keeps its
// query, e.g. a pre-filled New protocol link). Only a same-origin path is ever followed.
const KEY = "cellar.returnAfterLogin";

/** The path as the router will resolve it, or null when it leaves this origin. Parsing (not
 *  prefix checks) catches "/\\host" and "/<tab>/host", which a URL parser reads as "//host". */
function localPath(path: string): string | null {
  if (!path.startsWith("/")) return null;
  try {
    const url = new URL(path, window.location.origin);
    return url.origin === window.location.origin ? url.pathname + url.search + url.hash : null;
  } catch {
    return null;
  }
}

export function rememberPlace(path: string): void {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    // storage unavailable (private mode): sign-in lands on the home page
  }
}

/** The remembered page, read once; checked on read so a planted value is refused too. */
export function takePlace(): string | null {
  try {
    const path = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return path ? localPath(path) : null;
  } catch {
    return null;
  }
}
