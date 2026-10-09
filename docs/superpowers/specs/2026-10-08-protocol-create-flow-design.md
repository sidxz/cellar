# Protocol create flow: category first, forms, siblings, units

**Date:** 2026-10-08 · **Status:** design approved section by section; spec awaiting review
**Sub-project 1 of 6** from the chemist's-eye review of the ChEMBL fit test
(`docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md`, C1-C16). This one covers C1, C2, C5, C7, C8, C11, C16.
Later sub-projects, each with its own spec: 2 facts in chemists' words (C3, C4), 3 families and provenance (C9, C10),
4 conditions drive discriminators (C6), 5 workspace setup and defaults (C13-C15), 6 targets from Cellar (C12).

## Goal

A chemist registers a real assay by answering only what the assay needs, in the order they think about it. Measured on
the 21 ChEMBL protocols: about 15 interactions each, Type corrected by hand on 17, BAO assay format looked up on all 21,
siblings' discriminators fixed later on another protocol's page. Success:

- No Type correction and no BAO lookup on the create path for a category with a form.
- The interaction count per protocol roughly halves (category, facts, readout units, create).
- A new sibling never leaves another protocol flagged when its creator could have fixed it in the same step.

## Decisions (user, 2026-10-08)

- **Forms tied to categories.** Reuse Protocol Forms; a form names the category it serves; picking a category applies its
  form. No defaults on `ProtocolCategory` itself, no merge of the two concepts.
- **Siblings in one step.** When a new protocol shares its base name with protocols that have no discriminator, the
  create dialog asks for theirs too and one save sets all.
- **Units:** a canonical picker with aliases ("uM" finds µM), free text still allowed, stored in canonical spelling.
- **Dose Unit:** shown only when a readout fits dose-response curves; in vivo dose is a condition (mg/kg).
- **Category-first dialog** (section 1 sketch); Type and Assay format move under "More details".
- **Change from the approved section 2, for review:** the derived "assay format follows the target type" rule is dropped.
  SACLAB-DEV's curated catalog files 131 enzyme and binding protocols under BAO *biochemical format*; the shipped Enzyme
  inhibition and Binding forms use that, matching the lab's convention, so no derivation is needed.

## 1. The dialog

```
New protocol
┌ Category      [Growth inhibition ▾]                      first, focused
│ Organism      [M. tuberculosis ×] [Search…]              only the facts the category's pattern needs
│ NAME  M. tuberculosis growth inhibition                  live preview (code note: "assigned on create")
│ ⚠ PRT-00004 is also "M. tuberculosis growth inhibition"   only when siblings have no discriminator
│   This one:  [hypoxia   ]    PRT-00004 becomes … [MABA   ]
│ Starts from  [IC50 (dose-response) ▾]                    the category's forms; applied on category pick
│ Readouts     IC50  [µM ▾]  dose-response   (more)         compact rows
│              + Add readout
│ Also known as [LORA ×] [+]
│ ▸ More details   Type · Assay format · Targets · Cell line · Detection · Description · Project ·
│                  Conditions · Dose unit (only with a dose-response readout)
│ ▸ 2 similar protocols                                    one line; full box only for a run candidate
└ [Create protocol]
```

- **Order.** Category, then the facts its pattern requires (`requiredNameSlots`, already in the frontend): `{target}` →
  target picker, `{organism}` → organism, `{cell_line}` → cell line, `{matrix}` → assay format. A fact the pattern does
  not need stays under More details.
- **Name preview** sits under the facts. The discriminator field shows only when the pattern places `{discriminator}`, when
  siblings exist, or when the chemist opens it ("+ method or condition"), so a unique protocol is never asked for one.
- **Type and Assay format** are set by the form and live under More details; editable there and on the Design tab.
- **Draft retention** (close and reopen keeps entries) is kept; the dialog footer says "Draft kept" when reopened with
  entries, with a "Clear" action.
- **Keyboard:** Category is focused on open; Enter in a picker selects; Escape closes an open popover before the dialog.

## 2. Forms tied to categories

### Model

- `ProtocolForm.category_id: uuid | None`, a real FK to `protocol_categories.id`, `ON DELETE SET NULL` (a deleted
  category turns its forms generic). An id, not the label, so a category rename keeps its forms.
- `is_default` now means "the default form for its category"; at most one per category and at most one generic default
  (`category_id IS NULL`). Enforced by a partial unique index on `(workspace_id, coalesce(category_id, nil-uuid))
  WHERE is_default`, and by the aggregate's repository check.
- Existing forms migrate as generic; the current workspace default stays the generic default.

### Which form applies

On category pick: the category's default form; else its only form; else the generic default; else none (readouts,
Type and conditions stay as they are). "Starts from" lists the category's forms first, then generic forms, then
"Blank". Changing it re-applies.

### Applying a form

- Type, conditions and Dose Unit from the form.
- Readouts replaced only when the chemist has not edited them since the last apply; otherwise a confirm: "Replace your
  readouts with the form's?" (today they are overwritten silently).
- Facet defaults merge per slot and never replace a slot the chemist already filled (today the whole map is replaced).
- All readout template fields carry over, including pick-list values, calculated formula and dose-response config
  (today only name, data type, unit, aggregation, normalizations do).

### Shipped default forms

"Add default categories" also adds these forms (each the default for its category). Admin → Protocol Forms gets
"Add default forms" for workspaces that already have categories (SACLAB-DEV, SACLAB-IT). Readouts in the table are
`name (unit, data type)`; d-r = dose-response with an IC50-style curve; BAO format by label and id.

| Category | Type | Assay format (BAO) | Readouts | Conditions |
|---|---|---|---|---|
| Bactericidal activity | whole_cell | organism-based format `BAO_0000218` | MBC (µM) | |
| Binding | biochemical | biochemical format `BAO_0000217` | Kd (µM) | |
| Combination (checkerboard) | whole_cell | organism-based format | FICI | |
| Compound identity / purity | analytical | small-molecule physicochemical format `BAO_0000100` | Purity (%) | |
| Cytotoxicity | cell_based | cell based format `BAO_0000219` | CC50 (µM) | |
| Detection interference | biochemical | biochemical format | % inhibition (%) | |
| Enzyme activation | biochemical | biochemical format | EC50 (µM, d-r) | |
| Enzyme inhibition | biochemical | biochemical format | IC50 (µM, d-r) | |
| Growth inhibition: **IC50 (dose-response)**, default | whole_cell | organism-based format | IC50 (µM, d-r) | |
| Growth inhibition: **MIC** | whole_cell | organism-based format | MIC (µM) | |
| In vitro translation inhibition | biochemical | biochemical format | IC50 (µM, d-r) | |
| In vivo efficacy | in_vivo | organism-based format | log10 CFU reduction (log10 CFU) | Dose (mg/kg), Route (text) |
| Infection inhibition | cell_based | cell based format | EC50 (µM, d-r) | |
| Intrabacterial pH homeostasis | whole_cell | organism-based format | EC50 (µM, d-r) | |
| Intracellular growth inhibition | cell_based | cell based format | IC50 (µM, d-r) | |
| Ion-channel inhibition | cell_based | cell based format | IC50 (µM, d-r) | |
| Lipophilicity | physicochemical | small-molecule physicochemical format | LogD | pH |
| Membrane potential | whole_cell | organism-based format | EC50 (µM, d-r) | |
| Metabolic stability | admet | microsome format `BAO_0000251` | % remaining (%), CLint (µL/min/mg) | Incubation time (min) |
| Metabolite rescue | whole_cell | organism-based format | MIC (µM) | Metabolite (text) |
| Permeability | admet | cell based format | Papp (10-6 cm/s) | |
| Pharmacokinetics | in_vivo | organism-based format | Cmax (ng/mL), AUC (ng·h/mL), t1/2 (h) | Dose (mg/kg), Route (text) |
| Plasma protein binding | admet | plasma format `BAO_0020003` | Fraction unbound (fraction) | |
| Plasma stability | admet | plasma format | % remaining (%) | Incubation time (min) |
| Prediction | in_silico | none | Prediction score | |
| Receptor function | cell_based | cell based format | EC50 (µM, d-r) | |
| Resistance selection | whole_cell | organism-based format | Frequency of resistance | |
| Solubility | physicochemical | small-molecule physicochemical format | Solubility (µM) | |

Dose Unit defaults to µM in every form.

### New categories

The "Add category" dialog gets **Start protocols like** [existing category ▾]: copies that category's default form to the
new category (so Gametocytocidal activity can start like Growth inhibition: whole-cell, organism-based). Optional.

### Admin → Protocol Forms

Forms grouped by category; category picker on each form; unit picker on readout and condition units; facet defaults
editable (organism, cell line, assay format, detection) with the same ontology pickers as the dialog. Saving no longer
sends `ontology_defaults: null` (today it silently wipes them).

## 3. Siblings in one step

- The name preview already returns `siblings` (protocol id, code, name, discriminator). For each sibling **without** a
  discriminator the dialog shows "PRT-00004 becomes <base> [ ____ ]" and its new name live; the collision check covers
  the new protocol and every sibling's new name together.
- `CreateProtocolCommand.sibling_discriminators: list[{protocol_id, discriminator, reason | None}]`. `CreateProtocol`
  sets each in the same unit of work through `ProtocolNameService` (rename audit, "formerly" alias), after creating the
  new protocol:
  - **Draft sibling:** discriminator set (same editor rule as `SetDiscriminator`).
  - **Unlocked published sibling:** a correction; `reason` required; the dialog prefills "Distinguish from the new
    <code> (<name>)", editable.
  - **Locked or retired sibling:** not offered; flagged `needs discriminator` as today, and the dialog says so.
- A blank sibling field leaves that sibling flagged (today's behaviour; the banner button opens its editor later).
- Any failure (stale version, clash, permission) rolls back everything; the dialog names the protocol.

## 4. Units

- **Catalog** `domain/shared/units.py`: canonical spellings with spelling-only aliases (never across different units:
  mg/L is not an alias of µg/mL).

| Canonical | Aliases |
|---|---|
| µM, nM, mM, pM, M | uM, μM (Greek mu), umol/L, µmol/L; nmol/L; mmol/L; pmol/L; mol/L |
| µg/mL, ng/mL, mg/mL | ug/mL, μg/mL, ug/ml, µg/ml; ng/ml; mg/ml |
| mg/kg | mg/Kg, mpk |
| %, fold, fraction | percent, pct; x |
| log10 CFU, CFU/mL | log CFU, log10CFU, logCFU; cfu/mL, CFU/ml |
| h, min, s, d | hr, hrs, hour, hours; mins, minute, minutes; sec; day, days |
| µL/min/mg, mL/min/g liver, mL/min/kg | uL/min/mg, μL/min/mg |
| 10-6 cm/s | 1e-6 cm/s, x10-6 cm/s |
| ng·h/mL | ng*h/mL, h*ng/mL, ng.h/mL |
| °C, RFU, RLU, AU, mP, OD600, counts, peak area, Da | deg C, degC, °c |

- `canonical_unit(text) -> str | None`: trims; maps an alias (case-insensitive except where case carries meaning:
  `M`, `mM`, `mP`) to its canonical spelling; returns other text unchanged; blank → None.
- Applied on write in the application layer for readout, condition and form-template units (create, update, form CRUD,
  CDD import path included).
- `GET /api/v1/units` returns the catalog (canonical + aliases); orval regenerated in the same change.
  `UnitPicker` (shared component) is a combobox matching canonical or alias text, with free text allowed.
- **Data migration:** rewrites stored readout, condition and form-template units that are exact catalog aliases
  (SACLAB-DEV holds both `uM` and `µM` today). Units are display and export metadata; IC50 fits use the `dose_unit` enum.

## 5. Readouts, Dose Unit, nicknames, similar panel

- **Readout rows:** name and unit visible; "more" reveals data type, aggregation, normalizations, calculated/formula,
  pick list, curve settings. Defaults come from the form.
- **Dose Unit** is shown only when a readout has data type `dose_response`; otherwise the form's value is kept.
- **Nicknames at create:** `CreateProtocolCommand.nicknames: list[str]`, added through `Protocol.add_nickname` in the same
  unit of work, same validation as `AddProtocolNickname`.
- **Similar protocols:** one line "N similar protocols ▸" that expands to the list; the full box stays for a run
  candidate ("Log a run of this").

## 6. Changes by layer

- **Domain:** `ProtocolForm.category_id`; default-per-category rule; `domain/shared/units.py` (`canonical_unit`,
  catalog); shipped default forms (data, beside `DEFAULT_CATEGORY_PATTERNS`).
- **Application:** form CRUD takes `category_id`; `AddDefaultForms`; `AddDefaultCategories` also adds forms;
  `CreateProtocolCategory` accepts `start_like_category_id`; `CreateProtocol` takes `sibling_discriminators` and
  `nicknames`; unit canonicalization in readout, condition and form-template writers; `ListUnits` query.
- **Infrastructure:** migration `protocol_forms.category_id` + partial unique index; data migration for unit aliases.
- **Interface:** form routes (category, defaults), `POST /protocol-forms/defaults`, `GET /units`, create-protocol request
  gains `sibling_discriminators` and `nicknames` (additive; daikon unaffected), category create gains
  `start_like_category_id`. orval regenerated.
- **Frontend:** create dialog restructure (section 1), `UnitPicker`, form apply/merge rules, sibling fields, collapsed
  similar panel, Protocol Forms admin (grouping, category, facet defaults, Add default forms), Add category "Start
  protocols like".

## 7. Tests

- **Domain:** unit catalog and `canonical_unit` (aliases, case rules, unknown text, blank); form default-per-category rule.
- **Application:** form selection (category default, only form, generic default, none); `AddDefaultForms` idempotent;
  sibling discriminators (draft, published with reason, locked refused, rollback on clash or stale version); nicknames at
  create; unit canonicalization on every writer.
- **Integration:** forms migration and partial unique index; unit data migration; category delete turns forms generic.
- **API:** create with siblings and nicknames; `/units`; form CRUD with category; defaults endpoint.
- **Frontend:** category-first order and required-fact placement; form apply and per-slot facet merge; confirm before
  replacing edited readouts; sibling fields and combined collision; Dose Unit rule; `UnitPicker` alias match and free
  text; collapsed similar panel; Draft kept / Clear.
- **Browser walk:** re-enter a TCAMS-style family (3D7 pLDH, Dd2 pLDH, LDH counterscreen) and an Mtb pair (MABA,
  hypoxia) in a scratch workspace; count interactions against the 15-per-protocol baseline.

## Out of scope (later sub-projects)

Organism quick picks, common names and Strain (2); new-from-this on drafts, references, bulk entry (3); conditions as
discriminator source (4); first-run checklist, parasite categories, library grouping (5); requesting targets from Cellar,
home organisms (6).
