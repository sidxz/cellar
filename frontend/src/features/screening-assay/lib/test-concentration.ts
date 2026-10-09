/** Conditions that define a protocol become discriminator suggestions, and a concentration
 *  typed into a readout name ("% inhibition at 2 µM") moves into the condition it belongs to. */

/** The condition fields these helpers read and write; the create form's condition rows fit it. */
export interface ConditionDraft {
  name: string;
  data_type: string;
  unit?: string | null;
  pick_list_values?: string[] | null;
  fixed_value?: string | null;
}

export const TEST_CONCENTRATION = "Test concentration";

const CONCENTRATION_PHRASE = /\bat\s+(\d+(?:\.\d+)?)\s*(nM|µM|uM|mM|µg\/mL|mg\/mL)\b/;

/** "hypoxia", "72 h", "2 µM": each fixed value as a discriminator would read it. */
export function fixedConditionChips(conditions: ConditionDraft[]): string[] {
  const chips = new Map<string, string>();
  for (const cd of conditions) {
    const value = (cd.fixed_value ?? "").trim();
    if (!value) continue;
    const unit = cd.unit?.trim();
    const chip =
      cd.data_type === "numeric" ? (unit ? `${value} ${unit}` : value) : value.toLowerCase();
    if (!chips.has(chip.toLowerCase())) chips.set(chip.toLowerCase(), chip);
  }
  return [...chips.values()];
}

// The backend canonicalizes every unit on save; this spells the typed forms the way it will.
const canonicalUnit = (unit: string) => unit.replace(/^u/, "µ");

/** The concentration a readout name carries, or null. */
export function readoutTestConcentration(name: string): { value: string; unit: string } | null {
  const m = CONCENTRATION_PHRASE.exec(name);
  return m ? { value: m[1] as string, unit: canonicalUnit(m[2] as string) } : null;
}

/** The readout name without its concentration, and the conditions with "Test concentration"
 *  added or, when it exists, set to that value and unit. Null when the name has none. */
export function moveTestConcentration(
  name: string,
  conditions: ConditionDraft[],
): { name: string; conditions: ConditionDraft[] } | null {
  const found = readoutTestConcentration(name);
  if (!found) return null;
  const condition: ConditionDraft = {
    name: TEST_CONCENTRATION,
    data_type: "numeric",
    unit: found.unit,
    pick_list_values: [],
    fixed_value: found.value,
  };
  const exists = conditions.some((c) => c.name.trim() === TEST_CONCENTRATION);
  return {
    name: name.replace(CONCENTRATION_PHRASE, "").replace(/\s+/g, " ").trim(),
    conditions: exists
      ? conditions.map((c) => (c.name.trim() === TEST_CONCENTRATION ? { ...c, ...condition } : c))
      : [...conditions, condition],
  };
}
