#!/usr/bin/env node
// Pre-`next dev` guard:
//  1. Refuses to start if another `next dev --turbopack` is already running.
//  2. Wipes the Turbopack persistent cache if it has grown past LIMIT_GB.
//
// Turbopack has no built-in size cap as of Next 16; without this, the cache
// grows monotonically across sessions (we hit 25 GB once — see CLAUDE.md
// 2026-05-17 handoff). 3 GB is ~3x a normal first-compile baseline (~900 MB).
//
// Bypass either check with SKIP_DEV_GUARD=1.

import { rmSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";

const CACHE = ".next/dev/cache/turbopack";
const LIMIT_GB = 3;
const BYPASS = process.env.SKIP_DEV_GUARD === "1";

function tryRun(file, args) {
  try {
    return execFileSync(file, args, { encoding: "utf8" }).trim();
  } catch (err) {
    if (err.code === "ENOENT") return null;       // binary missing on host
    if (typeof err.status === "number") return "";// non-zero exit (pgrep no-match)
    throw err;
  }
}

if (!BYPASS) {
  const out = tryRun("pgrep", ["-f", "next dev --turbopack"]);
  if (out) {
    const list = out.split("\n").join(", ");
    console.error(`\nAnother 'next dev --turbopack' is already running (pid ${list}).`);
    console.error("  Stop it:    make stop   (or kill the PIDs above)");
    console.error("  Bypass:     SKIP_DEV_GUARD=1 pnpm dev\n");
    process.exit(1);
  }
}

try {
  statSync(CACHE);
  const duOut = tryRun("du", ["-sk", CACHE]);
  if (duOut) {
    const kb = parseInt(duOut.split(/\s+/)[0], 10);
    const gb = kb / 1024 / 1024;
    if (gb > LIMIT_GB) {
      console.log(`Turbopack cache ${gb.toFixed(1)} GB > ${LIMIT_GB} GB cap — wiping (one cold rebuild follows).`);
      rmSync(CACHE, { recursive: true, force: true });
    }
  }
} catch (err) {
  if (err.code !== "ENOENT") throw err;
}
