"use client";

/**
 * SourceProtocolsList — Task 9.1
 *
 * Renders the snapshotted source_protocols array from a closed campaign.
 * Each item is a Record<string, unknown> (the backend serialises a ProtocolSnapshot
 * object that hasn't got a strict Pydantic-level OpenAPI schema yet, so orval
 * emits { [key: string]: unknown }).
 */

interface SourceProtocolsListProps {
  protocols: Array<Record<string, unknown>>;
}

export function SourceProtocolsList({ protocols }: SourceProtocolsListProps) {
  if (!protocols || protocols.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        No source protocols recorded.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {protocols.map((p, i) => {
        const id = String(p.id ?? "");
        const name = String(p.name ?? "Unknown protocol");
        const version = p.version ?? p.protocol_version;
        const target = p.target_name ?? p.target;

        return (
          <li key={id || i} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-muted-foreground/40 mt-1.5" />
            <span>
              <span className="font-medium">{name}</span>
              {version != null && (
                <span className="text-muted-foreground ml-1.5">v{String(version)}</span>
              )}
              {target != null && (
                <span className="text-muted-foreground ml-1.5">— {String(target)}</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
