import type { CompoundCurvesTarget } from "@/features/screening-assay/components/compound-curves-dialog";
import type { Protocol } from "@/features/screening-assay/types";

/** What the curves dialog opens for these compounds in this protocol; null
 *  unless the protocol has measured curves and there is a compound. */
export function curvesTarget(
  protocol: Protocol | undefined,
  molecules: readonly { id: string; name: string }[],
): CompoundCurvesTarget | null {
  if (protocol?.has_measured_curves !== true || molecules.length === 0) return null;
  return { protocol: { id: protocol.id, name: protocol.name }, molecules: [...molecules] };
}

/** A compound as the curves dialog names it: registration number, else name. */
export function compoundRef(mol: { id: string; registration_number?: string; name?: string }) {
  return { id: mol.id, name: mol.registration_number || mol.name || "Compound" };
}
