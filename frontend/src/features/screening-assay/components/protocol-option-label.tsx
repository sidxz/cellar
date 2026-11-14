interface ProtocolOptionLabelProps {
  code?: string | null;
  name: string;
  /** Wrap a long name instead of truncating it. Pickers that list protocols
   *  side by side need the full name: the bracketed method suffix that tells
   *  sibling assays apart sits at the end, where truncation cuts. */
  wrap?: boolean;
}

/** Protocol in a picker: the code first (stable, short), then the generated name. */
export function ProtocolOptionLabel({ code, name, wrap = false }: ProtocolOptionLabelProps) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      {code && <span className="shrink-0 font-mono text-xs text-muted-foreground">{code}</span>}
      <span className={wrap ? "min-w-0 break-words" : "truncate"}>{name}</span>
    </span>
  );
}
