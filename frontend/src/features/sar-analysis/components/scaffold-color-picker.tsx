import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

export type ScaffoldColorProtocol = { id: string; name: string };

type Props = {
  protocols: ScaffoldColorProtocol[];
  value: string | null;
  onChange: (value: string | null) => void;
};

const NONE = "__none__";

/**
 * Picks a protocol whose activity colors the scaffold tree nodes.
 *
 * Hidden entirely when the result set has no protocols with activity — a
 * dropdown that always reads "— none —" is dead weight (the chemist
 * surfaced this on the 900-mol smoke). The label "Color by:" prefixes the
 * current value so the control's purpose is readable at a glance, no
 * hover required.
 */
export function ScaffoldColorPicker({ protocols, value, onChange }: Props) {
  if (protocols.length === 0) return null;

  return (
    <div className="inline-flex items-center gap-1 shrink-0">
      <span className="text-xs text-muted-foreground">Color by:</span>
      <Select
        value={value ?? NONE}
        onValueChange={(v) => onChange(v === NONE ? null : v)}
      >
        <SelectTrigger className="h-7 text-xs w-auto max-w-[200px] min-w-[120px]">
          <SelectValue placeholder="none" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>none</SelectItem>
          {protocols.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
