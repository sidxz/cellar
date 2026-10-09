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

const stripConcentration = (name: string) =>
  name.replace(CONCENTRATION_PHRASE, "").replace(/\s+/g, " ").trim();

const sameConcentration = (
  a: { value: string; unit: string },
  b: { value: string; unit: string },
) =>
  Number(a.value) === Number(b.value) &&
  canonicalUnit(a.unit.trim()) === canonicalUnit(b.unit.trim());

/** Why moving this readout's concentration would lose or contradict a fact, or null when the
 *  move is safe. `otherReadoutNames` are the protocol's other readouts. */
export function testConcentrationMoveBlocker(
  name: string,
  conditions: ConditionDraft[],
  otherReadoutNames: string[],
): string | null {
  const found = readoutTestConcentration(name);
  if (!found) return null;
  const others = otherReadoutNames.map((n) => readoutTestConcentration(n));
  if (others.some((c) => c && !sameConcentration(c, found)))
    return "Two concentrations: keep them in the names, or make Test concentration vary per run.";
  const existing = conditions.find((c) => c.name.trim() === TEST_CONCENTRATION);
  const fixed = existing?.fixed_value?.trim();
  if (fixed && !sameConcentration({ value: fixed, unit: existing?.unit ?? "" }, found)) {
    const at = [fixed, existing?.unit?.trim()].filter(Boolean).join(" ");
    return `Test concentration is already fixed at ${at}: keep this one in the name.`;
  }
  const stripped = stripConcentration(name).toLowerCase();
  if (otherReadoutNames.some((n) => n.trim().toLowerCase() === stripped))
    return `Another readout is already named "${stripConcentration(name)}": keep the concentration in the name.`;
  return null;
}

/** The readout name without its concentration, and the conditions with "Test concentration"
 *  added or, when it exists without a different fixed value, set to that value and unit.
 *  Null when the name has none or the move is blocked (see testConcentrationMoveBlocker). */
export function moveTestConcentration(
  name: string,
  conditions: ConditionDraft[],
  otherReadoutNames: string[] = [],
): { name: string; conditions: ConditionDraft[] } | null {
  const found = readoutTestConcentration(name);
  if (!found || testConcentrationMoveBlocker(name, conditions, otherReadoutNames)) return null;
  const condition: ConditionDraft = {
    name: TEST_CONCENTRATION,
    data_type: "numeric",
    unit: found.unit,
    pick_list_values: [],
    fixed_value: found.value,
  };
  const exists = conditions.some((c) => c.name.trim() === TEST_CONCENTRATION);
  return {
    name: stripConcentration(name),
    conditions: exists
      ? conditions.map((c) => (c.name.trim() === TEST_CONCENTRATION ? { ...c, ...condition } : c))
      : [...conditions, condition],
  };
}
