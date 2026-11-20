// The page a signed-out visitor asked for, so sign-in can return there (a deep link keeps its
// query, e.g. a pre-filled New protocol link). Only a same-origin path is ever followed.
const KEY = "cellar.returnAfterLogin";

const isLocalPath = (path: string) =>
  path.startsWith("/") && !path.startsWith("//") && !path.startsWith("/\\");

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
    return path && isLocalPath(path) ? path : null;
  } catch {
    return null;
  }
}
