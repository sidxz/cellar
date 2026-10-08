# Protocol names generated from structured fields

**Date:** 2026-10-08 · **Status:** design approved section by section; spec awaiting review
**Context:** protocol names are free text today. The legacy vault shows where that ends: 851 protocols that were
195 assays, 37% of names carrying a compound set, stage or date. The curated catalog (SACLAB-DEV) settled a naming
rule (subject + measurement, method only on collision) and the rule "where the name must echo a field, generate it
from the field". This spec makes the name a generated label, adds a stable code as the citation handle, and adds
aliases so people still find protocols by the names they actually say.

## Decisions (user, 2026-10-08)

- **Names are generated, never typed.** Each protocol category carries a name pattern; the name is that pattern
  filled from the protocol's fields.
- **One free part: the discriminator.** A method (`[resazurin]`) or a fixed defining condition (`[hypoxia]`).
  Required only when two protocols would otherwise share a name, and then on **both**.
- **Patterns are admin-editable, seeded with shipped defaults** for every category.
- **A pattern may place the discriminator** (`{subject?} {discriminator} prediction`); otherwise it trails in `[ ]`.
- **Target-based protocols link a registry target.** prot-cellar draft targets are near-future scope, not built:
  a missing target is created in prot-cellar as a plain target. No free-text provisional targets in Cellar.
- **Names never contain `·`, an em dash or an en dash.** Hyphens inside terms (`SARS-CoV-2`) are fine.
- **Immutable protocol code** (`PRT-00142`) is the citation handle; versions share it.
- **Aliases:** every former name automatically, plus nicknames (MABA, LORA, HLM CLint). Never part of the name.
- **Names re-derive when inputs change.** Relabels propagate automatically; a fact change on a published protocol
  is a correction with a required reason; a different assay is a new protocol with a new code.
- **End-of-implementation deliverable:** a visual walkthrough in Claude-in-Chrome of every change, setting and
  first-time setup step (section 7 is the running list).

## 1. How a name is built

**Name = the category's pattern, rendered.** If the pattern does not contain `{discriminator}` and the protocol
has one, it is appended as ` [discriminator]`.

### Slots

| Slot | Filled from |
|---|---|
| `{target}` | Direct registry target(s) in registry spelling, joined with `/` (coupled or complex systems only; a selectivity panel is one protocol per target). Prefixed with the target organism's short label when it is not the workspace home organism. Inherited (run) targets never feed the name. |
| `{organism}` | Organism facet (NCBITaxon) short label. |
| `{cell_line}` | **New Cell line facet**: a cell line or a cell type. Ontology sources CLO, then CL. |
| `{matrix}` | Assay format facet (BAO) short label. |
| `{subject}` | First filled of target, organism, cell line. |
| `{discriminator}` | The protocol's discriminator. |

`{slot?}` is optional and dropped when empty. A slot without `?` makes its field **required**: create and edit
refuse to save without it, and the form names the missing field. Rendering collapses whitespace. A registry target
at the start keeps its own case (`hERG inhibition`). Otherwise the first letter is capitalized only when the first
word is plain lowercase ASCII (`Kinetic solubility`, `Macrophage cytotoxicity`); a word with its own capitals or a
non-ASCII letter is left alone (`pLDH interference`, `β-Hematin formation inhibition`).

### Shipped default patterns

| Category | Pattern | Example |
|---|---|---|
| Enzyme inhibition | `{target} inhibition` | `PptT inhibition [FP]` |
| Enzyme activation | `{target} activation` | |
| Binding | `{target} binding` | `GlcB binding [nanoDSF]` |
| Receptor function | `{target} {discriminator}` | `Kinin receptor activation` (discriminator = mode) |
| Ion-channel inhibition | `{target} inhibition` | `hERG inhibition` |
| Growth inhibition | `{organism} growth inhibition` | `M. tuberculosis growth inhibition [hypoxia]` |
| Bactericidal activity | `{organism} bactericidal activity` | |
| Intracellular growth inhibition | `Intracellular {organism} growth inhibition` | |
| Metabolite rescue | `{organism} metabolite rescue` | |
| Membrane potential | `{organism} membrane potential` | `E. coli membrane potential` |
| Resistance selection | `{organism?} resistant mutant selection` | |
| Combination (checkerboard) | `{subject?} combination` | |
| Cytotoxicity | `{cell_line} cytotoxicity` | `HepG2 cytotoxicity [CellTiter-Glo]` |
| Infection inhibition | `{organism} infection inhibition` | `SARS-CoV-2 infection inhibition` |
| In vitro translation inhibition | `{organism} in vitro translation inhibition` | |
| Intrabacterial pH homeostasis | `{organism} intrabacterial pH disruption` | |
| Detection interference | `{discriminator} interference` | `AMC quenching interference` |
| Metabolic stability | `{matrix} stability` | `Microsomal stability` |
| Plasma stability | `Plasma stability` | |
| Plasma protein binding | `Plasma protein binding` | |
| Permeability | `{cell_line?} permeability` | `Caco-2 permeability` |
| Solubility | `{discriminator?} solubility` | `Kinetic solubility` |
| Lipophilicity | `Lipophilicity` | `Lipophilicity [LogD]` on collision |
| Pharmacokinetics | `{organism?} pharmacokinetics` | |
| In vivo efficacy | `{organism} in vivo efficacy` | `Cryptosporidium in vivo efficacy` |
| Compound identity / purity | `Compound identity and purity` | |
| Prediction | `{subject?} {discriminator} prediction` | `Mdh docking score prediction` |

A category an admin adds gets the generic pattern `{subject?} {category}` until edited.

### Short labels

Each ontology term used in a name has a short label: admin-editable overrides on top of computed defaults.

- NCBITaxon species label: `Genus epithet` → `G. epithet` (`M. smegmatis`); below species the rest is kept
  (`Plasmodium falciparum 3D7` → `P. falciparum 3D7`).
- NCBITaxon one-word label (genus): `Genus spp.` (`Mycobacterium spp.`).
- Virus names are never abbreviated (`Zika virus`).
- CLO labels drop a trailing ` cell` (`Vero cell` → `Vero`).
- BAO format labels drop ` format`.
- Shipped overrides: Homo sapiens → `Human`; Mus musculus → `Mouse`; Rattus norvegicus → `Rat`; Severe acute respiratory syndrome-related coronavirus → `SARS-CoV-2`;
  Middle East respiratory syndrome-related coronavirus → `MERS-CoV`; Bacteria → `Bacterial`; Alphavirus →
  `Alphavirus`; Cryptosporidium → `Cryptosporidium`; microsome format → `Microsomal`; plasma format → `Plasma`.
- Registry targets carry organism as text, not a taxon id: the target organism's short label is the override for
  the NCBITaxon term with that label, else the species rule.

### Discriminator

- A method or a fixed defining condition. At most 40 characters. Autocompletes from discriminators already used on
  the same base name.
- Rejected: stage words (HTS, retest, primary screen, hit confirmation, dose response, IC50, single point,
  triplicate), names of library collections, years and dates, version marks (v2, corrected, before, after, new,
  old).
- On collision both protocols need one; the existing protocol is flagged `needs discriminator` and its owner sees
  the prompt until it is set.

### Characters

No `·`, `—` or `–` in any name. Pattern and short-label editors refuse them; the generator replaces any that arrive
from outside (registry spelling) with a space or hyphen.

## 2. Identity and recall

### Protocol code

- Immutable, workspace-scoped, minted at create: prefix + zero-padded number (`PRT-00142`). Prefix and width are
  workspace settings beside the molecule registration-number ones (default `PRT-`, 5), same validation
  (`^[A-Z]{2,8}-$`), same minting (per-workspace advisory lock, MAX+1). Never reused.
- Versions share the code: `PRT-00142` is the assay, `PRT-00142 v2` a version. A reference by code resolves to the
  latest active version unless a version is given.
- Shown beside the name in the detail header, library rows, pickers, run pages and audit entries; its own column in
  every export. Chart legends keep the name only.

### Aliases

- **Former names**: appended on every rename with date and reason; searchable; shown as "formerly …".
- **Nicknames**: editors add or remove freely; not unique (an ambiguous nickname returns every match); same
  character rule as names; the discriminator guard does not apply.
- Shown under "Also known as" on the protocol page and in the library row tooltip. Never rendered as the name.

### Search

Library search, protocol pickers and global search match on name, code, aliases, registry target name and gene
symbol, organism and cell line labels, condition values, and discriminator. A hit says which field matched
("matched alias: MABA").

## 3. Change and renames

### Triggers

The stored name is re-derived when an input changes:
- the protocol's category, direct targets, Organism / Cell line / Assay format annotations, discriminator (same
  transaction as the change);
- a linked target's registry name or organism (target sync compares old and new spelling and emits
  `TargetRenamed`; a handler re-derives every protocol linked to it);
- a category pattern, a short label, the workspace home organism (admin edits).

### Three kinds of change

| Kind | Rule |
|---|---|
| **Relabel** (same facts, different words) | Automatic on every affected protocol, any status. One audit entry per protocol with the reason; the old name becomes an alias. Admin edits show a before → after preview of every affected protocol and cannot be confirmed while they would create a collision. |
| **Correction** (a fact on a published protocol was wrong) | Allowed on unlocked published protocols with a **required reason** and a preview of the new name. Same code. Drafts need no reason. Locked and retired protocols refuse. |
| **Different assay** (the experiment changed) | Not an edit: "Create new protocol from this one" copies it under a new code; the original keeps its name and data. Versions remain for refinements within one assay and always share the name. |

Editing a name-affecting field on a published protocol asks: *Correction, or did the assay change?* Category and
ontology annotations, editable only on drafts today, become editable on unlocked published protocols through the
correction path only. Readout and condition definition rules are unchanged.

### References

- Cross-protocol formulas reference the code: `@{PRT-00142}.{IC50}`. The editor autocompletes by name and inserts
  the code. Name resolution is removed (no formula uses it today).
- daikon keys on protocol id; responses gain `code`, `discriminator`, `aliases` (additive). Announce before merge.
- Exports carry name and code. Audit entries show the name at the time and the current name.

### Collisions

- Person-initiated (create, edit, admin pattern or label edit): blocked until a discriminator resolves it; the
  clashing protocol is named.
- Sync-initiated (registry rename): applied; both protocols flagged `name conflict`; library badge plus an admin
  list.
- Uniqueness: the full name is unique per workspace across codes (versions of one code share it). Enforced in the
  application layer, since sync-initiated conflicts must be representable.

## 4. Model changes by layer

### Domain
- `ProtocolNamingPolicy` (pure, `domain/screening_assay/protocol_naming.py`): render a pattern from `NamingInputs`
  (targets, organism, cell line, matrix, discriminator, short labels, home organism) → name or the missing slots;
  `validate_discriminator`; character normalization; default short-label rules and shipped overrides; shipped
  default patterns.
- `Protocol`: `code` (immutable), `discriminator`, `aliases` (VO list: label, kind `former|nickname`, at, reason),
  `name_flag` (`needs_discriminator | name_conflict | None`). `name` is set only through
  `apply_derived_name(name, reason)`, which records the former name and emits `ProtocolRenamed`. `update()` loses
  `name`. Correction-path setters take `reason` and are allowed on unlocked ACTIVE.
- `ProtocolCategory` (workspace_config aggregate): `label` (unique per workspace), `name_pattern`. Replaces the
  "Protocol Categories" controlled vocabulary (its 27 terms migrate). Protocols keep the category label; a label
  rename is a relabel.
- `NamingLabel` (workspace_config): `term_id` → short label override.
- `WorkspaceSettings`: `protocol_code_prefix`, `protocol_code_width`, `home_organism_term_id`.
- Events: `ProtocolRenamed` (old, new, reason), `TargetRenamed`.

### Application
- `ProtocolNameService`: gathers inputs (targets, labels, category pattern, home organism) and renders; used by
  create, update, annotation, target add/remove, discriminator and alias use cases, and by relabel handlers.
- Queries: `PreviewProtocolName` (live preview: name, missing fields, collision), `PreviewNamingChange` (admin
  pattern/label edit: before → after list, collisions), `ListNameFlags`.
- Commands: `SetDiscriminator`, `AddProtocolAlias` / `RemoveProtocolAlias` (nicknames), `CreateProtocolFromExisting`,
  `ProtocolCategory` CRUD, `NamingLabel` CRUD; correction variants of category / annotation / target changes carry
  `reason`.
- `CrossProtocolResolver` resolves codes.
- Handlers: `TargetRenamed` → re-derive linked protocols; category/label/home-organism change → re-derive affected.

### Infrastructure
- Migration: `protocols.code`, `protocols.discriminator`, `protocols.name_flag`; `protocol_aliases` table
  (protocol_id, label, kind, at, reason; trigram index); `protocol_categories`; `naming_labels`; settings keys.
- `SyncTargets` detects name and organism changes and emits `TargetRenamed`.
- Cell line ontology slot (CLO, CL) seeded with the other facet slots.

### Interface and UI
- Routes: name preview, naming-change preview, aliases, discriminator, categories, labels, name flags; protocol DTO
  gains `code`, `discriminator`, `aliases`, `name_flag`. orval regenerated in the same change.
- Create dialog: no name field; live name preview; required facts per category; discriminator field with
  autocomplete and guard messages. `suggest-protocol-name.ts` and the "Suggest name" button are removed.
- Protocol page: code in the header, "Also known as" with nickname editing, discriminator; correction-or-new-assay
  dialog.
- Admin: Protocol Categories (pattern editor with live examples, reset to default, before → after preview), Short
  labels, Workspace settings (code prefix/width, home organism), name-flag list.
- Library: code column, wider search with match reason, flag badges. Formula editor inserts codes. Exports add
  code.

## 5. Rollout

1. Foundations: code, aliases, search, formulas by code, Cell line facet.
2. Naming: categories with patterns, short labels, generator, live preview, discriminator guard, collisions.
3. Change handling: target-sync rename detection, admin edit previews, correction dialog, new-protocol-from-this,
   flags.
4. Migration of the 214 SACLAB-DEV protocols (195 curated + 19 older):
   - codes minted in creation order;
   - the 53 curated protocols whose targets are missing from prot-cellar: list reviewed with the user, targets
     created in prot-cellar as plain targets **after the user confirms**, synced, linked;
   - Cell line, genus-level organism and discriminator filled from the curated decisions;
   - the 19 older protocols curated one by one; facts proposed to the user;
   - category corrections proposed with the list: Redox cycling detection moves to Detection interference; a
     "Protein-protein interaction inhibition" category (`{target} interaction inhibition`) for the RNA polymerase /
     NusG assay, today filed as Binding; a target decision for Unspecified enzyme inhibition;
   - dry run of all names; every changed name read individually; full before → after list to the user before
     applying; current names become former-name aliases; the two Pks13 duplicate pairs resolved;
   - `load_curated.py` moved to the new create path.
5. daikon informed before merge.

## 6. Tests

- Domain: pattern rendering, optional and required slots, short-label rules and overrides, capitalization,
  character rule, discriminator guard.
- Golden fixture (~30 facet sets from the curated catalog, facets only, committed) with expected names.
- Integration: code minting under concurrency; collision blocking vs flagging; `TargetRenamed` propagation;
  correction requires a reason; alias search.
- API: formula references by code; name preview; naming-change preview.
- Frontend: live preview, guard messages, pattern editor preview, correction dialog.

## 7. Walkthrough (running list for the Chrome tour)

**First-time setup**
1. Workspace settings: protocol code prefix and width, home organism.
2. Protocol Categories: patterns (shipped defaults, live examples, reset).
3. Short labels.
4. Cell line ontology slot.
5. Missing targets created in prot-cellar, then target sync.

**Daily use**
1. Create a protocol: no name field, live name, required facts, discriminator.
2. Collision: both protocols asked for a discriminator.
3. Protocol page: code, "Also known as", adding a nickname.
4. Edit a published protocol: correction (reason) or new assay (new code).
5. Library: search by code, alias, condition value; flag badges.
6. Formula editor inserting a code.
7. Export with the code column.
8. Activity log: rename entries with reasons; "formerly" aliases.
9. Live demo: rename a target in prot-cellar, sync, watch linked protocols rename.

## Out of scope

- prot-cellar draft targets (near-future, separate). When they ship, the mirror carries their status and Cellar
  shows a "draft target" badge; nothing else here changes.
- Comparability-aware data views (splitting SAR columns by defining conditions): separate track, but a
  prerequisite for long-term trust in generic names.
- Rename notifications, relabel undo, ChEMBL deposition.
