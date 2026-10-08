interface ProtocolOptionLabelProps {
  code?: string | null;
  name: string;
}

/** Protocol in a picker: the code first (stable, short), then the generated name. */
export function ProtocolOptionLabel({ code, name }: ProtocolOptionLabelProps) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      {code && <span className="shrink-0 font-mono text-xs text-muted-foreground">{code}</span>}
      <span className="truncate">{name}</span>
    </span>
  );
}
