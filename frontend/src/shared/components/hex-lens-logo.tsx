/** Brand mark — magnifier whose lens is a benzene ring: chemical search.
 *  Source art: docs/branding/hex-lens-logo.svg (32 grid, crisp at 16-128px).
 *  Same as the product site's logo: hexagon takes the accent colour,
 *  handle uses currentColor, both follow the theme. */
export function HexLensLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <polygon
        points="14,6.5 20.5,10.25 20.5,17.75 14,21.5 7.5,17.75 7.5,10.25"
        fill="none"
        stroke="var(--ds-accent)"
        strokeWidth="2.4"
      />
      <line x1="20.3" y1="17.55" x2="26.1" y2="23.35" stroke="currentColor" strokeWidth="3.2" />
    </svg>
  );
}
