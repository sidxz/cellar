# InChIKey collapses rac/rel enhanced stereo into the single enantiomer

**Found:** 2026-09-10, while auditing molecule uniqueness (migration 073 added the
unique active-InChIKey index).

Standard InChI reads every stereocentre as absolute and drops enhanced stereo
groups, so through `StructureStandardizer` today:

| input | InChIKey |
|---|---|
| `C[C@H](N)C(=O)O` (S)-alanine | `QNAYBMKLOCPYGJ-REOHCLBHSA-N` |
| `C[C@H](N)C(=O)O \|&1:1\|` racemate drawn with wedges (AND group) | `QNAYBMKLOCPYGJ-REOHCLBHSA-N` (same) |
| `C[C@H](N)C(=O)O \|o1:1\|` relative (OR group) | `QNAYBMKLOCPYGJ-REOHCLBHSA-N` (same) |
| `CC(N)C(=O)O` flat | `QNAYBMKLOCPYGJ-UHFFFAOYSA-N` |

`RegisterMolecule` therefore silently DEDUPLICATES a rac/rel-annotated
registration into the single enantiomer (or the reverse), and the new unique
index enforces the same identity. The business rule "racemic mixture is its own
entry" (`docs/domain-model/10-business-rules.md`) only holds when the racemate is
drawn flat. The annotation is not lost — `cxsmiles` keeps `|&1:1|` / `|o1:1|` and
`registration_provenance.disclosed_smiles` keeps the raw input — but identity
ignores it.

**Fix direction:** identity = InChIKey + a stereo-flavour derived from RDKit
`StereoGroup`s (`abs` / `and` / `or` / none). Persist it as a small column,
include it in `find_by_inchi_key` and in `uq_molecules_ws_inchi_active`, and
surface it on the molecule card. Cheaper interim: reject `&`/`o` groups at
registration with a message telling the chemist to draw racemates flat.
