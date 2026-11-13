"use client";

import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";

interface SegmentOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

/** A small one-of-several switch, as tabs. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as T)}>
      <TabsList aria-label={label}>
        {options.map((o) => (
          <TabsTrigger key={o.value} value={o.value} disabled={o.disabled} className="text-xs">
            {o.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
