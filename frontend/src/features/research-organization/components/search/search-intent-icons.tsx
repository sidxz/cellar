import type { ReactNode } from "react";

function SearchIntentIcon({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.65}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function AssayActivityIcon({ className }: { className?: string }) {
  return (
    <SearchIntentIcon className={className}>
      <path d="M4 3v17h17" />
      <path d="M7 17h2c6 0 1-10 7-10h5" />
      <path d="M4 12h2m7 8v-2" />
      <circle cx="9" cy="17" r=".75" fill="currentColor" stroke="none" />
      <circle cx="16" cy="7" r=".75" fill="currentColor" stroke="none" />
    </SearchIntentIcon>
  );
}

export function MolecularStructureIcon({ className }: { className?: string }) {
  return (
    <SearchIntentIcon className={className}>
      <path d="m10 4 6 3.5v7L10 18l-6-3.5v-7L10 4Z" />
      <path d="m10 6.8 3.5 2m0 4.2-3.5 2M6.5 13V9" />
      <path d="m16 7.5 3.8-2.2m-3.8 9.2 3.8 2.2" />
      <circle cx="21" cy="4.6" r="1.4" />
      <circle cx="21" cy="17.4" r="1.4" />
    </SearchIntentIcon>
  );
}

export function CompoundIdentifiersIcon({ className }: { className?: string }) {
  return (
    <SearchIntentIcon className={className}>
      <rect x="2.5" y="5" width="19" height="14" rx="2" />
      <path d="M6 9h4m-2 0v6m-2 0h4m3-6h2a3 3 0 0 1 0 6h-2V9Z" />
    </SearchIntentIcon>
  );
}
