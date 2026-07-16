"use client";

import { useId } from "react";

/** Brand mark — magnifier whose lens is a benzene ring: chemical search.
 *  Source art: docs/branding/hex-lens-logo.svg (32 grid, crisp at 16-128px).
 *  Handle uses currentColor to adapt to theme; gradient is still DocuStore's
 *  spectrum palette — re-color when a chem-vault identity exists. */
export function HexLensLogo({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient
          id={id}
          gradientUnits="userSpaceOnUse"
          x1="7.5"
          y1="21.5"
          x2="20.5"
          y2="6.5"
        >
          <stop offset="0" stopColor="#37d7fa" />
          <stop offset="0.4" stopColor="#4b72fe" />
          <stop offset="0.68" stopColor="#ff8df2" />
          <stop offset="1" stopColor="#ff8705" />
        </linearGradient>
      </defs>
      <polygon
        points="14,6.5 20.5,10.25 20.5,17.75 14,21.5 7.5,17.75 7.5,10.25"
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="2.4"
      />
      <line x1="20.3" y1="17.55" x2="26.1" y2="23.35" stroke="currentColor" strokeWidth="3.2" />
    </svg>
  );
}
