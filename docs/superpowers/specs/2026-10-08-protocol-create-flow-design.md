# Protocol create flow: category first, forms, siblings, units

**Date:** 2026-10-08 · **Status:** design approved section by section; spec revised for generality, awaiting review
**Sub-project 1 of 6** from the chemist's-eye review (`docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md`,
C1-C16). This one covers C1, C2, C5, C7, C8, C11, C16. Later sub-projects, each with its own spec: 2 facts in chemists'
words (C3, C4), 3 families and provenance (C9, C10), 4 conditions drive discriminators (C6), 5 workspace setup and
defaults (C13-C15), 6 targets from Cellar (C12).

**Background.** The fit test (21 public TB and malaria assays entered by hand) showed the create dialog asks for facts in
an order that does not follow from the category, asks for the kind of assay three times, leaves units to free text,
and leaves siblings flagged for someone else to fix. Nothing below is tuned to that sample: every rule is driven by the
category's pattern, the registry target's type, or the workspace's own forms.

## Goal and success criteria

A chemist registers any assay by answering only what that assay needs, in the order they think about it.

- For any category with a form, creating a protocol needs no Type change and no assay-format lookup.
- The facts a category's pattern requires appear next to the category, for any pattern, built-in or admin-written.
- A new protocol that shares its base name with editable protocols resolves them in the same save.
- Any spelling of a unit (uM, μM, umol/L) is stored one way.
- Verified by a browser walk in a scratch workspace: one protocol per shipped category, plus a family of three siblings,
  counting interactions per protocol.

## Decisions (user, 2026-10-08)

- **Forms tied to categories.** Reuse Protocol Forms; a form names the category it serves; picking a category applies
  its form. No defaults on `ProtocolCategory` itself, no merge of the two concepts.
- **Siblings in one step.** When a new protocol shares its base name with protocols that have no discriminator, the
  create dialog asks for theirs too and one save sets all.
- **Units:** canonical spelling by general rules, a picker of common units, free text still allowed.
- **Dose Unit:** shown only when a readout fits dose-response curves; in vivo dose is a condition.
- **Category-first dialog** (section 1); Type and Assay format move under "More details".
- **General, not example-tuned (user):** defaults and rules must hold for any lab. Where a category has more than one
  common readout convention, each ships as its own form and none is preselected.

## 1. The dialog

```
New protocol
┌ Category      [Enzyme inhibition ▾]                      first, focused
│ Target        [PptT ×] [Select…]                         the facts this category's pattern needs
│ NAME  M. tuberculosis PptT inhibition                    live preview
│ ⚠ PRT-00004 is also "M. tuberculosis PptT inhibition"     only when siblings have no discriminator
│   This one:  [FP        ]    PRT-00004 becomes … [AlphaScreen]
│ Starts from  ( IC50 dose-response ) ( % inhibition single point )   the category's forms
│ Readouts     IC50  [µM ▾]  dose-response   (more)         compact rows
│              + Add readout
│ Also known as [ +]
│ ▸ More details   Type · Assay format · other facts · Description · Project · Conditions ·
│                  Dose unit (only with a dose-response readout)
│ ▸ 2 similar protocols                                    one line; full box only for a run candidate
└ [Create protocol]
```

- **Facts by pattern.** Category, then the facts its pattern requires (`requiredNameSlots`): `{target}` → target picker,
  `{organism}` → organism, `{cell_line}` → cell line, `{matrix}` → assay format. A required `{subject}` shows the target
  picker when the applied form follows the target, otherwise the organism picker; the other two stay one click away
  under More details. Facts the pattern does not need stay under More details. Same rules for admin-written patterns.
- **Name preview** under the facts. The discriminator field shows only when the pattern places `{discriminator}`, when
  siblings exist, or when the chemist opens it ("+ method or condition"); a unique protocol is never asked for one.
- **Starts from** shows the category's forms as one-click choices (section 2); with a default form it is preselected.
- **Type and Assay format** are set by the form (and the target, see 2) and live under More details; editable there and
  on the Design tab.
- **Draft retention** is kept; when reopened with entries the footer says "Draft kept" with a "Clear" action.
- **Keyboard:** Category focused on open; Enter in a picker selects; Escape closes an open popover before the dialog.

## 2. Forms tied to categories

### Model

- `ProtocolForm.category_id: uuid | None`, a real FK to `protocol_categories.id`, `ON DELETE SET NULL` (a deleted
  category turns its forms generic). An id, so a category rename keeps its forms.
- `ProtocolForm.assay_format_from_target: bool` (default false): when true and the protocol has direct targets, the assay
  format follows the targets' registry type (mapping below); otherwise the form's own assay-format default applies.
- `is_default` means "the default form for its category"; at most one per category and at most one generic default
  (`category_id IS NULL`): partial unique index on `(workspace_id, coalesce(category_id, nil-uuid)) WHERE is_default`,
  plus the repository check. Existing forms migrate as generic; an existing workspace default stays the generic default.

### Target type → assay format

Covers every registry `TargetType`. With several targets, the format applies only if they all map to the same one;
otherwise the form's default stays.

| Target type | BAO assay format |
|---|---|
| single_protein, domain | single protein format `BAO_0000357` |
| protein_complex, protein_protein_interaction | protein complex format `BAO_0000223` |
| protein_family | protein format `BAO_0000224` |
| nucleic_acid | nucleic acid format `BAO_0000225` |
| organism | organism-based format `BAO_0000218` |
| cell_line | cell based format `BAO_0000219` |
| tissue | tissue-based format `BAO_0000221` |
| unknown | none (form's default stays) |

Why a flag and not always: a target-based assay can run in cells (an ion channel or receptor measured in a cell line);
its form keeps cell based format and does not follow the target.

### Which form applies

On category pick: the category's default form, if any; else, if the category has exactly one form, that one; else the
generic default when the category has no forms; else nothing is applied and "Starts from" asks for one click. Readouts,
Type and conditions are left as they are while nothing is applied. Changing "Starts from" re-applies.

### Applying a form

- Type, conditions and Dose Unit from the form; assay format from the target when the form says so, else the form's.
- Readouts replaced only when the chemist has not edited them since the last apply; otherwise a confirm: "Replace your
  readouts with the form's?" (today they are overwritten silently).
- Facet defaults merge per slot and never replace a slot the chemist already filled (today the whole map is replaced).
- All readout template fields carry over, including pick-list values, calculated formula and dose-response config
  (today only name, data type, unit, aggregation, normalizations do).

### Shipped default forms

Added by "Add default categories"; Admin → Protocol Forms gets "Add default forms" (idempotent) for workspaces that
already have categories. General conventions only. Where a category has more than one common readout convention, each is
its own form and **none is the default** (one click under "Starts from"); a workspace admin can make one the default.
Readouts are `name (unit)`; d-r = data type dose_response with an IC50-style curve; single = single point.

| Category | Forms (readouts) | Type | Assay format | Conditions |
|---|---|---|---|---|
| Enzyme inhibition | IC50 d-r (µM) · % inhibition single (%) | biochemical | from target; else biochemical format `BAO_0000217` | |
| Enzyme activation | EC50 d-r (µM) · % activation single (%) | biochemical | from target; else biochemical format | |
| Binding | Kd (µM) · ΔTm thermal shift (°C) | biochemical | from target; else biochemical format | |
| Receptor function | EC50 d-r (µM) | cell_based | cell based format `BAO_0000219` | |
| Ion-channel inhibition | IC50 d-r (µM) | cell_based | cell based format | |
| Growth inhibition | MIC (µM) · IC50 d-r (µM) · % inhibition single (%) | whole_cell | organism-based format `BAO_0000218` | |
| Bactericidal activity | MBC (µM) | whole_cell | organism-based format | |
| Intracellular growth inhibition | IC50 d-r (µM) | cell_based | cell based format | |
| Metabolite rescue | MIC (µM) | whole_cell | organism-based format | Metabolite (text) |
| Membrane potential | EC50 d-r (µM) | whole_cell | organism-based format | |
| Resistance selection | Frequency of resistance | whole_cell | organism-based format | Selecting concentration (µM) |
| Combination (checkerboard) | FICI | whole_cell | organism-based format | |
| Cytotoxicity | CC50 d-r (µM) | cell_based | cell based format | |
| Infection inhibition | EC50 d-r (µM) | cell_based | cell based format | |
| In vitro translation inhibition | IC50 d-r (µM) | biochemical | cell-free format `BAO_0000366` | |
| Intrabacterial pH homeostasis | EC50 d-r (µM) | whole_cell | organism-based format | |
| Detection interference | % inhibition single (%) | biochemical | biochemical format | |
| Metabolic stability | % remaining (%), CLint (µL/min/mg) | admet | microsome format `BAO_0000251` | Incubation time (min) |
| Plasma stability | % remaining (%) | admet | plasma format `BAO_0020003` | Incubation time (min) |
| Plasma protein binding | Fraction unbound (fraction) | admet | plasma format | |
| Permeability | Papp (10-6 cm/s) | admet | cell based format | |
| Solubility | Solubility (µM) | physicochemical | small-molecule physicochemical format `BAO_0000100` | pH |
| Lipophilicity | LogD | physicochemical | small-molecule physicochemical format | pH |
| Compound identity / purity | Purity (%) | analytical | small-molecule physicochemical format | |
| Pharmacokinetics | Cmax (ng/mL), AUC (ng·h/mL), t1/2 (h) | in_vivo | organism-based format | Dose (mg/kg), Route (text) |
| In vivo efficacy | Efficacy (none; unit chosen per study) | in_vivo | organism-based format | Dose (mg/kg), Route (text) |
| Prediction | Prediction score | in_silico | none | |

Dose Unit defaults to µM in every form. A category with a single shipped form gets it as its default; a category with
several has no default.

### New categories

The "Add category" dialog gets **Start protocols like** [existing category ▾]: copies that category's forms (and its
default choice) to the new category. Optional; without it the new category has no forms until an admin adds one.

### Admin → Protocol Forms

Forms grouped by category; category picker and "Assay format follows the target" on each form; unit picker on readout
and condition units; facet defaults editable (any facet slot) with the same ontology pickers as the dialog. Saving no
longer sends `ontology_defaults: null` (today it silently wipes them).

## 3. Siblings in one step

- The name preview returns `siblings` (protocol id, code, name, discriminator). For each sibling **without** a
  discriminator the dialog shows "<code> becomes <base> [ ____ ]" and its new name live; the collision check covers the
  new protocol and every sibling's new name together.
- `CreateProtocolCommand.sibling_discriminators: list[{protocol_id, discriminator, reason | None}]`. `CreateProtocol`
  sets each in the same unit of work through `ProtocolNameService` (rename audit, "formerly" alias), after creating the
  new protocol:
  - **Draft sibling:** discriminator set (same editor rule as `SetDiscriminator`).
  - **Unlocked published sibling:** a correction; `reason` required; the dialog prefills "Distinguish from the new
    <code> (<name>)", editable.
  - **Locked or retired sibling:** not offered; flagged `needs discriminator` as today, and the dialog says so.
- A blank sibling field leaves that sibling flagged (the banner button opens its editor later).
- Any failure (stale version, clash, permission) rolls back everything; the dialog names the protocol.

## 4. Units

### Canonical spelling by rule

`canonical_unit(text) -> str | None` in `domain/shared/units.py`. Applied token by token; a token is split off by `/`,
`·`, `*`, or a `.` between letters. Unknown tokens are left exactly as typed, so any unit (ug/kg, nmol/min/mg, U/mL)
normalizes consistently without a list.

1. Trim; collapse inner whitespace; blank → None.
2. **Micro prefix:** a leading `u`, `μ` (Greek mu) or `mc` directly before a base symbol (`M`, `mol`, `g`, `L`, `l`,
   `m`, `s`) becomes `µ` (micro sign): uM → µM, ug → µg, μL → µL. `U` (enzyme units) is untouched.
3. **Litre:** a base `l` becomes `L`: ml → mL, ul → µL, dl → dL.
4. **Molar:** `<prefix>mol/L` becomes `<prefix>M`: umol/L → µM, nmol/L → nM.
5. **Mass:** `Kg` becomes `kg`.
6. **Words:** hr, hrs, hour(s) → h; mins, minute(s) → min; sec(s), second(s) → s; day(s) → d; percent, pct → %;
   deg C, degC, °c → °C.
7. **Products:** `*` or `.` between unit tokens → `·` (ng*h/mL → ng·h/mL).

Case is otherwise preserved (`M` is molar, `m` is milli or metre); nothing converts between different units.

### Where it applies

- On write in the application layer for readout, condition and form-template units (create, update, form CRUD, the CDD
  import path).
- `GET /api/v1/units` returns a suggestion list of common canonical units for the picker (concentration, mass
  concentration, dose, percent and ratio, time, clearance, permeability, signal); orval regenerated in the same change.
  `UnitPicker` (shared) is a combobox over the suggestions; matching treats `u`/`μ` as `µ` and ignores case, and free
  text is always accepted. Canonicalization happens only in the backend; the saved, canonical unit is what the form
  shows after save (one implementation of the rules, no frontend copy).
- **Data migration** rewrites every stored readout, condition and form-template unit whose canonical spelling differs.
  Units are display and export metadata; IC50 fits use the `dose_unit` enum.

## 5. Readouts, Dose Unit, nicknames, similar panel

- **Readout rows:** name and unit visible; "more" reveals data type, aggregation, normalizations, calculated/formula,
  pick list, curve settings. Defaults come from the form.
- **Dose Unit** is shown only when a readout has data type `dose_response`; otherwise the form's value is kept.
- **Nicknames at create:** `CreateProtocolCommand.nicknames: list[str]`, added through `Protocol.add_nickname` in the same
  unit of work, same validation as `AddProtocolNickname`.
- **Similar protocols:** one line "N similar protocols ▸" that expands to the list; the full box stays for a run
  candidate ("Log a run of this").

## 6. Changes by layer

- **Domain:** `ProtocolForm.category_id`, `assay_format_from_target`, default-per-category rule;
  `domain/shared/units.py` (`canonical_unit`, suggestion list); target-type → assay-format mapping; shipped default
  forms (data, beside `DEFAULT_CATEGORY_PATTERNS`).
- **Application:** form CRUD with the new fields; `AddDefaultForms`; `AddDefaultCategories` also adds forms;
  `CreateProtocolCategory` accepts `start_like_category_id`; `CreateProtocol` takes `sibling_discriminators` and
  `nicknames`; unit canonicalization in every unit writer; `ListUnits` query.
- **Infrastructure:** migration (`protocol_forms.category_id`, `assay_format_from_target`, partial unique index); unit
  data migration.
- **Interface:** form routes, `POST /protocol-forms/defaults`, `GET /units`, create-protocol request gains
  `sibling_discriminators` and `nicknames` (additive; existing API consumers unaffected), category create gains
  `start_like_category_id`. orval regenerated.
- **Frontend:** create dialog restructure (section 1), `UnitPicker`, form apply and merge rules, assay format from target,
  sibling fields, collapsed similar panel, Protocol Forms admin, Add category "Start protocols like".

## 7. Tests

- **Domain:** `canonical_unit` rule table (each rule, unknown tokens untouched, case kept, no cross-unit conversion,
  enzyme `U` untouched); target-type mapping covers every `TargetType`; form default-per-category rule.
- **Application:** form selection (default, single form, generic, none → ask); `AddDefaultForms` idempotent; sibling
  discriminators (draft, published with reason, locked not offered, rollback on clash or stale version); nicknames at
  create; unit canonicalization on every writer.
- **Integration:** forms migration and partial unique index; unit data migration; category delete turns forms generic.
- **API:** create with siblings and nicknames; `/units`; form CRUD with category; defaults endpoint.
- **Frontend:** required facts placed by pattern (built-in and admin patterns, including `{subject}`); form apply and
  per-slot facet merge; assay format follows the target only when the form says so (single protein vs complex vs mixed
  targets); confirm before replacing edited readouts; one-click "Starts from" when there is no default; sibling fields
  and combined collision; Dose Unit rule; `UnitPicker` matching (`uM` finds µM) and free text; collapsed similar panel; Draft kept / Clear.
- **Browser walk** (scratch workspace): one protocol per shipped category, one family of three siblings; interactions per
  protocol recorded.

## Out of scope (later sub-projects)

Organism quick picks, common names and Strain (2); new-from-this on drafts, references, bulk entry (3); conditions as
discriminator source (4); first-run checklist, parasite categories, library grouping (5); requesting targets from Cellar,
home organisms (6).
