# A tab link to a run loses its hash on a full page load

Found 2026-11-12 while checking the Curves tab. Recorded, not fixed.

## What happens

Opening a run URL that ends in a tab hash in a fresh page load (pasted link, bookmark, reload after navigating elsewhere) lands on Readout Data, and the hash is gone from the address bar. Seen for `#files` and `#curves` on `/assays/runs/{id}`. Clicking a tab inside the page sets the hash correctly; only the full load loses it.

It is not specific to the Curves tab: `#files`, a tab that has existed for a long time, behaves the same.

## Probable cause (not verified)

The hash is already missing by the time the run page reads it, so the tab hook (`frontend/src/shared/hooks/use-hash-tab.ts`) falls back to its default. The likely place is the sign-in check on a full load: `frontend/src/app/auth/callback/page.tsx` returns the user with `router.replace(returnTo ?? "/")`, and a return path built from the pathname and query string carries no fragment. A fragment is never sent to the server, so anything that round-trips through a redirect has to carry it explicitly.

## Why it matters

Links to a specific tab of a run cannot be shared or bookmarked.

## Proposed fix

Confirm where the hash is dropped (log `location.hash` at page mount and in the auth callback). If it is the sign-in round trip, include the fragment in the return path. Then add a test for the tab hook's first render with a hash present.
