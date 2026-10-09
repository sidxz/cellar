# Ontology search ranks derivatives above the exact term

**Found:** 2026-10-08, create-flow walk (docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md, W4).

**Symptom.** Searching the cell-line picker for "HepG2" lists "HepG2-AhR-luc", "ARE-bla HepG2" and
"HepG2-CYP2B6-hCAR" before the parental line "Hep G2 cell" (4th). Searching the organism picker for "Mus musculus" lists
the subspecies "Mus musculus musculus" before the species "Mus musculus". A chemist picking the first hit records the
wrong cell line or taxon, and the protocol name follows the wrong term.

**Root cause.** `BioPortalClient.search` (backend/src/cellar/infrastructure/external/bioportal/client.py) passes
BioPortal's own ranking straight through, requesting only `prefLabel`. BioPortal's ranking favours partial label
matches. "HepG2" is a synonym of "Hep G2 cell", not its prefLabel, so nothing pulls the parental line up.

**Fix direction.** Request `include=prefLabel,synonym`. Stable-sort so that terms whose normalized prefLabel or synonym
equals the normalized query come first (case-, space- and hyphen-insensitive), keeping BioPortal's order within each
group. Pin it with a client test using a recorded response. No change to the response shape.

**Not done here.** This predates the create-flow branch (feat/protocol-create-flow) and affects every ontology picker,
so it gets its own change.
