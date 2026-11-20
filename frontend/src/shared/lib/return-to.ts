/**
 * A way back to the app that sent the scientist here (a `return_to` link parameter).
 *
 * Only an address on an origin listed in APP_RETURN_ORIGINS is followed, never a URL the
 * link alone supplies, so a link cannot turn ChemCellar into an open redirect. Shared by the
 * /api/config route (server) and the pages (client).
 */

export interface ReturnOrigin {
  label: string;
  origin: string;
}

export interface ReturnTarget {
  label: string;
  url: string;
}

function httpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/** `Label=origin` entries, comma-separated; anything else is dropped. */
export function parseReturnOrigins(raw: string | undefined): ReturnOrigin[] {
  const origins: ReturnOrigin[] = [];
  for (const entry of (raw ?? "").split(",")) {
    const at = entry.indexOf("=");
    const label = entry.slice(0, at).trim();
    const url = at > 0 ? httpUrl(entry.slice(at + 1).trim()) : null;
    if (label && url) origins.push({ label, origin: url.origin });
  }
  return origins;
}

export function trustedReturnTarget(
  returnTo: string | null,
  origins: readonly ReturnOrigin[],
): ReturnTarget | null {
  const url = returnTo ? httpUrl(returnTo) : null;
  const trusted = url && origins.find((o) => o.origin === url.origin);
  return trusted && returnTo ? { label: trusted.label, url: returnTo } : null;
}

/** The address to go back to, carrying the protocol when there is one. */
export function returnHref(target: ReturnTarget, protocolId?: string): string {
  if (!protocolId) return target.url;
  const url = new URL(target.url);
  url.searchParams.set("protocol_id", protocolId);
  return url.toString();
}
