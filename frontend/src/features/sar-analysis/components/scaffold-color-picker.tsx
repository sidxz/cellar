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

export function ScaffoldColorPicker({ protocols, value, onChange }: Props) {
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
    >
      <SelectTrigger className="w-full max-w-[240px]">
        <SelectValue placeholder="— none —" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>— none —</SelectItem>
        {protocols.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
