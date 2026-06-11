/**
 * Human-readable display for an R-group substituent fragment.
 *
 * R-group decomposition returns each substituent as a fragment SMILES carrying
 * the attachment point as a dummy atom — e.g. `N#C[*:1]`, `[H][*:2]`. Showing
 * that raw string in a table cell or heatmap axis is unreadable for a chemist,
 * so this maps the common substituents to compact, conventional labels (CN,
 * OMe, CF₃, …) with the full name on hover.
 *
 * Anything not in the curated dictionary falls back to a cleaned SMILES (the
 * `[*:n]` attachment rendered as a plain `*`) — we NEVER invent a name, because
 * a wrong label would erode trust in the whole table. The exact raw SMILES is
 * always kept (hover title + thumbnail source) so nothing is lost.
 *
 * Dictionary keys are the EXACT canonical forms RDKit's `RGroupDecompose`
 * (asSmiles=True) emits (dummy written last), verified against the backend
 * RDKit. The atom-map index (`:1`, `:2`, …) is the R-group number and is
 * collapsed before lookup, so the same substituent reads identically at R1, R2…
 */

/** Matches the attachment dummy in any R-position form: `[*:1]`, `[*:2]`, `[*]`. */
const ATTACHMENT_RE = /\[\*(?::\d+)?\]/g;

/** Canonical hydrogen fragment after atom-map normalization. */
const HYDROGEN_KEY = "[H][*:1]";

type KnownSubstituent = { label: string; name: string };

/**
 * Common substituents → {compact label, full name}. Keyed by the RDKit-canonical
 * fragment SMILES with the attachment dummy normalized to `[*:1]`.
 */
const SUBSTITUENT_NAMES: Record<string, KnownSubstituent> = {
  "F[*:1]": { label: "F", name: "fluoro" },
  "Cl[*:1]": { label: "Cl", name: "chloro" },
  "Br[*:1]": { label: "Br", name: "bromo" },
  "I[*:1]": { label: "I", name: "iodo" },
  "C[*:1]": { label: "Me", name: "methyl" },
  "CC[*:1]": { label: "Et", name: "ethyl" },
  "CC(C)[*:1]": { label: "iPr", name: "isopropyl" },
  "CC(C)(C)[*:1]": { label: "tBu", name: "tert-butyl" },
  "FC(F)(F)[*:1]": { label: "CF₃", name: "trifluoromethyl" },
  "O[*:1]": { label: "OH", name: "hydroxy" },
  "CO[*:1]": { label: "OMe", name: "methoxy" },
  "N[*:1]": { label: "NH₂", name: "amino" },
  "CN(C)[*:1]": { label: "NMe₂", name: "dimethylamino" },
  "N#C[*:1]": { label: "CN", name: "nitrile" },
  "O=[N+]([O-])[*:1]": { label: "NO₂", name: "nitro" },
  "NC(=O)[*:1]": { label: "CONH₂", name: "carboxamide" },
  "O=C(O)[*:1]": { label: "CO₂H", name: "carboxylic acid" },
  "CC(=O)[*:1]": { label: "Ac", name: "acetyl" },
  "COC(=O)[*:1]": { label: "CO₂Me", name: "methyl ester" },
  "NS(=O)(=O)[*:1]": { label: "SO₂NH₂", name: "sulfonamide" },
  "c1ccc([*:1])cc1": { label: "Ph", name: "phenyl" },
};

export type FragmentDisplay = {
  /** Compact text for the cell: a conventional label, "H", a cleaned SMILES, or "—". */
  label: string;
  /** Hover text: full chemical name + raw SMILES when known, else the raw SMILES. */
  title: string;
  /** True for `[H][*:n]` — an unsubstituted position. Render plainly, no thumbnail. */
  isHydrogen: boolean;
  /** Raw fragment SMILES to depict; null for hydrogen / empty (nothing to draw). */
  thumbnailSmiles: string | null;
};

/**
 * Resolve a substituent fragment SMILES to its chemist-facing display.
 * Pure + synchronous so it can drive an AG Grid cell renderer or a heatmap axis
 * header directly.
 */
export function fragmentDisplay(fragmentSmiles: string): FragmentDisplay {
  const raw = (fragmentSmiles ?? "").trim();
  if (!raw) {
    return { label: "—", title: "no substituent", isHydrogen: false, thumbnailSmiles: null };
  }

  const key = raw.replace(ATTACHMENT_RE, "[*:1]");

  if (key === HYDROGEN_KEY) {
    return { label: "–H", title: "unsubstituted (–H)", isHydrogen: true, thumbnailSmiles: null };
  }

  const known = SUBSTITUENT_NAMES[key];
  if (known) {
    return {
      label: known.label,
      title: `${known.name} — ${raw}`,
      isHydrogen: false,
      thumbnailSmiles: raw,
    };
  }

  // Unknown substituent: show a cleaned SMILES (attachment as `*`), never an
  // invented name. Keep the exact raw SMILES on hover and as the thumbnail.
  return {
    label: raw.replace(ATTACHMENT_RE, "*"),
    title: raw,
    isHydrogen: false,
    thumbnailSmiles: raw,
  };
}
