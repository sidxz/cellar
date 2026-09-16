import type { BlockerPayload } from "@/shared/lib/api/model";

function sampleText(sample: Record<string, unknown>): string {
  return (sample.label as string | null | undefined) ?? (sample.id as string);
}

/** Groups of rows that stop a delete (or that it will change): one line per group. */
export function DeleteBlockerList({ items }: { items: BlockerPayload[] }) {
  return (
    <ul className="list-disc pl-5">
      {items.map((b) => (
        <li key={`${b.table}:${b.fk_column}:${b.display_label ?? ""}`}>
          {b.display_label ? (
            <>
              {b.display_label} ({b.count})
            </>
          ) : (
            <>
              {b.count} {b.entity_type}
              {b.count !== 1 ? "s" : ""}
            </>
          )}
          {b.samples.length > 0 && (
            <span className="text-muted-foreground">
              : {b.samples.map((s) => sampleText(s as Record<string, unknown>)).join(", ")}
              {b.truncated ? ", …" : ""}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
