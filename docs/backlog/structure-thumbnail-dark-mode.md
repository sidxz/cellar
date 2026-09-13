# Structure depictions render washed out in dark mode

**Found:** 2026-09-12, while visually checking the new MCS core chip in both themes.

**Symptom:** every `StructureThumbnail` — scaffold chips in the R-group core picker, the new MCS
chip, and every other structure tile — draws on a cream/tan ground with pale, low-contrast bonds
under `data-theme="dark"`. In light mode the same tiles are white with black bonds and read fine.

**Scope:** pre-existing and app-wide, not specific to any one surface. All four chips in the core
picker show it identically, including the three that predate the MCS work.

**Root cause (unconfirmed):** the depiction itself carries a light ground rather than a transparent
one, so the wrapper's `bg-background` token never shows through. Worth checking whether the backend
`DepictionService` (`infrastructure/rdkit/depiction.py`) sets a background color on the RDKit
drawer, and whether the frontend `StructureThumbnail` can ask for a transparent one.

**Why it matters:** a chemist judges a candidate core by looking at it. A structure they have to
squint at is a structure they will not check — which undercuts the whole point of showing
candidates as pictures rather than SMILES.

**Fix direction:** render with a transparent background and theme-aware bond/atom colors, or keep a
white plate deliberately (a white card behind the drawing reads fine in dark mode and is what
several ELN products do). Either is defensible; the current in-between is not. One change, every
structure surface benefits.
