# ChEMBL TB + malaria naming fit test (SACLAB-IT, through the UI)

Plan: `docs/superpowers/plans/2026-10-08-chembl-ui-fit-test.md`. Branch `feat/protocol-auto-naming`; fixes from this
test are `b4921908` (naming) and `c13eecc8` (UI). Running document: updated as the test proceeds.

## UI bugs

| # | Where | Bug | Severity | Status |
|---|---|---|---|---|
| U1 | Admin → Ontology Slots → slot editor | Ontology Sources has no **CL (Cell Ontology)**. An admin `cell_line` slot overrides the standard one (CLO + CL) by name, so creating it from this editor silently drops CL. | Medium | fixed `c13eecc8`, verified in UI |
| U2 | New Protocol dialog | Category is labelled "(optional)", but create refuses without it. | Medium | fixed `c13eecc8`, verified in UI |
| U3 | Ontology search, workspace without a BioPortal key | Raw `API error: 503 — …` in the dropdown. | Medium | message fixed `c13eecc8`; setup gap S1 open |
| U4 | New Protocol dialog | Picking a category seemed to scroll the dialog to the facets. | — | not reproduced |
| U5 | Any full-page load | Every hard navigation re-runs `/auth/callback`; a few in quick succession land on `/login?error=Too many requests`. | Low (dev, auth) | backlog |
| U6 | New Protocol dialog → "Similar protocols exist" | Type chip shows the raw enum (`whole_cell`, `cell_based`, `in_vivo`, `admet`) instead of the label. | Low | fixed `32497577` |
| U7 | Protocols library (list view) | A row with the `needs discriminator` badge widens the table past the viewport: the page scrolls sideways, the header and **New Protocol** button are clipped, and once scrolled the main content slides under the fixed sidebar. Persists after the flag clears. | Medium | fixed `32497577` (live check pending sign-in) |
| U8 | Protocol page, banner "Other protocols share this name. Add a discriminator…" | Banner has no action; the discriminator is only editable under More → Edit details. Overview shows Discriminator "—" with no edit affordance. | Medium | fixed `32497577` (live check pending sign-in) |
| U9 | Protocol page → More → Edit details | Name preview says "The code is assigned when you create the protocol." on a protocol that already has its code. | Low | fixed `32497577` (live check pending sign-in) |
| U10 | New Protocol dialog → Targets picker | Options show name and type only, no organism. Two registry targets with the same name in different organisms (human DHODH vs P. falciparum DHODH) are indistinguishable. | Medium | fixed `32497577` (live check pending sign-in) |
| U11 | New Protocol dialog | "Targets (optional)" while the category needs a target (preview: "This name needs a target."); same for "Discriminator (optional)" when the pattern places `{discriminator}` (Detection interference, Receptor function, Prediction) and "Facets (optional)" when the pattern needs organism / cell line. Same class as U2. | Medium | fixed `32497577` (live check pending sign-in) |
| U12 | New Protocol dialog → "Similar protocols exist" | Matches on category alone: a P. falciparum growth assay lists M. tuberculosis ones; a biochemical InhA assay lists whole-cell Mtb assays. Noise, not help. | Low | fixed `32497577` (live check pending sign-in) |
| U13 | Edit details → sibling warning | 'Other protocols are also "Microsomal stability" (PRT-00019)' though PRT-00019 is "Microsomal stability [human]" (only the base matches). | Low | fixed `32497577` (live check pending sign-in) |
| U14 | Admin → Protocol Categories → New category | No live example of the pattern (spec section 4: "pattern editor with live examples"). | Low | won't fix (user): new categories have no protocols; edits show before → after |

Retracted: "Detection method facet without a slot" and "Cell line slot not seeded". The dialog always offers the four
standard facets (`use-protocol-facet-slots.ts`); admin slots only override them by name.

## Naming bugs (policy)

| # | Input | Before | After | Status |
|---|---|---|---|---|
| N1 | Detection interference, discriminator `pLDH` | `PLDH interference` | `pLDH interference` | fixed `b4921908`, PRT-00016 |
| N2 | Category pattern `β-Hematin formation inhibition` | `Β-Hematin…` (Greek capital) | `β-Hematin formation inhibition` | fixed `b4921908`, M12 |
| N3 | NCBITaxon strain / variant labels | unabbreviated | `P. falciparum 3D7` | fixed `b4921908` (moot for BioPortal terms, see F2) |
| N4 | NCBITaxon `Zika virus` | `Z. virus` | `Zika virus` | fixed `b4921908` |
| N5 | Mus musculus / Rattus norvegicus | `M. musculus pharmacokinetics` | `Mouse pharmacokinetics` | shipped labels added `b4921908` |

## Setup gaps

| # | Gap |
|---|---|
| S1 | A new workspace needs a BioPortal API key (`{workspace}:bioportal`) before any Organism / Cell line / Assay format can be picked. Missing from the spec's first-time setup list (section 7). SACLAB-IT got SACLAB-DEV's key copied through `CreateExternalApiKey`. |

## Fit findings (not bugs)

| # | Finding |
|---|---|
| F1 | **Strain lives in the discriminator.** ChEMBL keeps `assay_strain` apart from organism; Cellar has no strain facet, so 3D7 / Dd2 / H37Rv / BCG / MDR isolates all go in the discriminator. Works, but assays differing on two axes need compound discriminators (`[3D7 pLDH]`, `[3D7 SYBR Green]`, `[Dd2 pLDH]`). |
| F2 | **BioPortal NCBITaxon has no strain or "variant" taxa**: no P. falciparum 3D7 / Dd2, no M. bovis / BCG (taxid 33892 or 1765), only species and subspecies. Searching "Mycobacterium bovis BCG" returns ten unrelated *bovis* species. BCG was entered ChEMBL-style: organism M. tuberculosis, discriminator `BCG`. |
| F3 | **Species of a matrix assay does not reach the name.** Human vs mouse liver microsomes both render `Microsomal stability`; the organism facet is set but unused, so the collision forces `[human]` / `[mouse]` (user ruling: discriminator). |
| F4 | **Host organism of in vivo / intracellular assays does not reach the name** (`P. berghei in vivo efficacy`, `Intracellular P. yoelii growth inhibition`). ChEMBL files the P. berghei 4-day test under target Mus musculus (the host); Cellar's organism facet holds the pathogen. "Liver stage" is lost from the Novartis assay name; a nickname can carry it. |
| F5 | **No category for some standard antimalarial assays**: gametocytocidal activity, β-hematin (hemozoin) inhibition. An admin added both in the UI (`{organism} gametocytocidal activity`, fixed `β-Hematin formation inhibition`); worked first time. β-Hematin is a non-protein "target" in ChEMBL and correctly gets no registry target. |
| F6 | **Dose Unit has no mg/kg** (µM, nM, mM, mg/mL), so in vivo protocols cannot state their dose unit. |
| F7 | **CLO label `Hep G2 cell`** renders `Hep G2`; chemists write `HepG2`. Needs an admin short label. The engineered HepG2-A16-CD81 line is not in CLO. |
| F8 | **Registry names from prot-cellar's gene-derived default**: `PFF0160c` (Pf DHODH), `PF3D7_0417200` (DHFR-TS), `FP2A` (falcipain-2), `KCNH2` (hERG). P. falciparum genes often carry a locus tag as primary name. User ruling: curate to DHODH, DHFR-TS, Falcipain-2, hERG in prot-cellar before linking. |
| F9 | A complex target renders as its subunits: `M. tuberculosis GyrA/GyrB inhibition`; chemists say "DNA gyrase". Reads fine, matches the spec. |

## Protocols entered (SACLAB-IT)

| Code | ChEMBL | Name (UI) | Predicted? |
|---|---|---|---|
| PRT-00001 | CHEMBL3637831 GSK_TB MABA | M. tuberculosis growth inhibition [MABA] | yes (discriminator added after the clash) |
| PRT-00002 | CHEMBL1634497 LORA | M. tuberculosis growth inhibition [hypoxia] | yes |
| PRT-00003 | CHEMBL3637833 GSK_TB intracellular THP-1 | Intracellular M. tuberculosis growth inhibition | yes |
| PRT-00004 | CHEMBL3637834 GSK_TB MDR isolates | M. tuberculosis growth inhibition [MDR clinical isolates] | yes |
| PRT-00005 | CHEMBL890612 M. bovis BCG | M. tuberculosis growth inhibition [BCG] | changed: strain taxon unavailable (F2) |
| PRT-00006 | CHEMBL882762 MBC | M. tuberculosis bactericidal activity | yes |
| PRT-00007 | CHEMBL907779 InhA | M. tuberculosis InhA inhibition | yes |
| PRT-00008 | CHEMBL4406692 DprE1 | M. tuberculosis DprE1 inhibition | yes |
| PRT-00009 | CHEMBL3875318 gyrase supercoiling | M. tuberculosis GyrA/GyrB inhibition | yes |
| PRT-00010 | CHEMBL868352 Vero MTT | Vero cytotoxicity | yes |
| PRT-00011 | CHEMBL860322 mouse lung CFU | M. tuberculosis in vivo efficacy | yes |
| PRT-00012 | CHEMBL907401 mouse liver microsomes | Microsomal stability [mouse] | yes (after the clash) |
| PRT-00013 | CHEMBL1054500 GSK TCAMS 3D7 | P. falciparum growth inhibition [3D7 pLDH] | yes |
| PRT-00014 | CHEMBL1054501 GSK TCAMS Dd2 | P. falciparum growth inhibition [Dd2 pLDH] | yes |
| PRT-00015 | CHEMBL730079 St. Jude 3D7 SYBR | P. falciparum growth inhibition [3D7 SYBR Green] | yes |
| PRT-00016 | CHEMBL1054502 TCAMS LDH counterscreen | pLDH interference | yes, after fix N1 |
| PRT-00017 | CHEMBL1789905 Novartis liver stage | Intracellular P. yoelii growth inhibition | yes |
| PRT-00018 | CHEMBL713211 P. berghei 4-day | P. berghei in vivo efficacy | yes |
| PRT-00019 | CHEMBL623454 human liver microsomes | Microsomal stability [human] | yes |
| PRT-00020 | CHEMBL3389350 NF54 gametocytes | P. falciparum gametocytocidal activity | yes (new category) |
| PRT-00021 | CHEMBL4428589 β-hematin | β-Hematin formation inhibition | yes, after fix N2 (new category) |

Pending (need the curated prot-cellar target names): DHFR-TS mutant, falcipain-2, Pf DHODH, human DHODH, hERG.

## Chemist's-eye review of creating protocols (from this pass)

Measured on 21 protocols: about 15 interactions each, two to four BioPortal lookups at 3-4 s each, Type changed by hand
on 17 of 21, Assay format looked up by BAO jargon on all 21.

| # | Shortcoming | Evidence | Direction |
|---|---|---|---|
| C1 | **Field order fights the mental model.** Category, the field that decides the name and what is required, sits mid-dialog; its required companions (organism, target, cell line) are a scroll away under "Facets"; Discriminator comes first, before anyone knows if it is needed. | every protocol | Category first; show exactly the facts that category needs right under it; preview under them; discriminator only when a sibling exists. |
| C2 | **The kind of assay is said three times.** Type (Biochemical, Whole-cell…), Category (Growth inhibition…) and Assay format (BAO "organism-based format", "single protein format") encode the same thing. Type defaults to Biochemical whatever the category. | 17/21 Type edits; 21/21 BAO lookups | Derive Type and Assay format from Category (and target type: complex → protein complex format); editable later on Design. |
| C3 | **Organism search is slow and does not speak chemist.** 10 results, 3-4 s; "mouse" ranks Mus musculus 6th; "human" misses Homo sapiens; "Mtb" finds nothing; "Mycobacterium bovis BCG" returns ten unrelated *bovis* species. | probes | Workspace quick picks first (organisms and cell lines already used here, no network); common-name synonyms (Mtb, Pf, mouse, human, rat); exact match ranked first. |
| C4 | **Strain has no home.** TB and malaria whole-cell assays are defined by strain (H37Rv, Erdman, BCG, 3D7, Dd2, W2, NF54); BioPortal has none of them, so strain goes into the free-text discriminator mixed with method (`[3D7 pLDH]`, `[3D7 SYBR Green]`): order varies by person, no library filter by strain. | F1, F2 | Optional Strain field (prot-cellar already has a strains table) with a `{strain?}` slot: `P. falciparum 3D7 growth inhibition [pLDH]`. Discriminator back to method or condition. |
| C5 | **The discriminator lands on the wrong person, late.** The first protocol of a kind gets none; the second creator's protocol flags the first, whose owner must come back, and the first protocol's name changes under everyone who knew it. | PRT-00001, PRT-00012 | Ask for the method at create for categories that usually have variants (whole-cell growth inhibition), or let the second creator set both in one step ("PRT-00001 becomes … [MABA]"). |
| C6 | **Defining conditions are scattered.** Hypoxia went into the discriminator, "at 2 µM" into readout names, "72 h", "late-stage gametocytes" into description; Conditions sits at the bottom, unconnected to the name. | M1-M3, T2 | Suggest the discriminator from a defining condition; test concentration as a condition, not part of a readout name. |
| C7 | **Units are free text and doubled.** Readout unit is typed ("µ" is hard to type, so expect "uM"); Dose Unit is a separate field (µM/nM/mM/mg/mL) that is irrelevant for single-point, ADMET and in vivo, and has no mg/kg; MIC was entered in µg/mL under a µM dose unit. | F6 | Unit picker with canonical units (µM, nM, µg/mL, mg/kg, %, log10 CFU); Dose Unit only for dose-response, defaulted from category. |
| C8 | **Readouts demand full configuration up front.** At least one readout is required, with data type, aggregation, four normalization checkboxes and a calculated toggle that mean nothing for MIC/IC50/CC50. | every protocol | Readout presets per category (Growth inhibition → MIC or IC50; Cytotoxicity → CC50; Metabolic stability → % remaining, CLint; In vivo → log10 CFU reduction); advanced fields collapsed. |
| C9 | **Families of assays are typed from scratch.** TCAMS (3 assays), GSK TB set (5), St. Jude, Novartis pairs: each sibling repeats category, organism search, type, format, readout. "Duplicate" on a draft makes a new version under the same code; "New protocol from this one" only appears inside the published-protocol correction dialog. | M1-M3, T1-T4 | "New protocol from this" on drafts and library rows (prefill everything, ask for the discriminator or strain); bulk entry by CSV or ChEMBL assay id for catalog building. |
| C10 | **Provenance has no field.** Every protocol here came from a ChEMBL assay or paper; the id went into Description. | all | Typed references (ChEMBL assay, PubChem AID, DOI, SOP link), searchable. |
| C11 | **Names omit the words chemists search for.** MABA, LORA, TCAMS, "liver stage", "4-day Peters test" are not in the names (by design) and nothing prompts for nicknames at create. | T1, T2, M6, M7 | "Also known as" in the create dialog, suggested from the method. |
| C12 | **A missing target means leaving Cellar.** Sign in to prot-cellar (separate session and workspace), find the protein in a proteome, create, come back, sync; the name it gets (PFF0160c) then appears in protocol names and can only be fixed in prot-cellar. Human counterscreen targets read "Human hERG inhibition"; one home organism cannot cover a TB + malaria lab with human counterscreens. | F8 | Request a target from the Cellar picker (prefilled from ChEMBL/UniProt) with a curated name; several home organisms, or a rule for human counterscreens. |
| C13 | **New-workspace prerequisites are found by failing.** Default categories, the BioPortal key (found by typing an organism), Ontology Slots that look required but are not (creating one dropped CL). | S1, U1 | First-run checklist on the Protocols page. |
| C14 | **Default categories are bacteria-shaped.** No gametocytocidal, liver stage, transmission blocking (SMFA), parasite reduction ratio; "Bactericidal activity" for parasites. Adding one in Admin took a minute. | F5 | Ship parasite categories; "cidal activity" wording. |
| C15 | **Library defaults to Group by Target**; 16 of 21 whole-cell protocols land in "No target". Organism filter shows truncated Latin names. | library | Default group by Category or Organism for whole-cell-heavy workspaces; short labels in filters. |
| C16 | **Small frictions.** Similar-protocols panel takes a third of the first screen for little value now that exact clashes are blocked; Escape closes the dialog (draft kept, silently); a long form scrolls 1.5 screens. | every protocol | Collapse the panel to one line unless it is a run candidate; say "draft kept". |

Keep: the live name preview and its clash messages; the collision → flag → discriminator loop; codes; draft retention;
the category admin (fast, readable patterns); target-prefix and complex naming.

## Create flow walk (sub-project 1, branch feat/protocol-create-flow, 2026-10-08)

Suites: backend unit 3660 passed (PDF test deselected); integration + API 1253 passed, 2 failed (pre-existing
`TestMoleculeTestCounts`, docs/backlog/test-molecules-api-drift.md); frontend vitest 1355 passed / 1 skipped; lint and tsc
exit 0; ruff format clean; ruff check reports no finding in files this branch adds (3 pre-existing import-order findings
in files it touches). Migrations 089 → 087 → 089 round-trip clean (dev DB had no protocol forms, nothing dropped).

Walk in SACLAB-IT. "Add default forms" seeded 32 forms grouped by category; categories whose conventions differ (Binding,
Enzyme inhibition, Growth inhibition) preselect none. One protocol per distinct pattern shape (29 categories reduce to
these shapes); interactions counted from category pick to Create:

| Protocol | Shape | Interactions | Checked |
|---|---|---|---|
| PRT-00022 P. falciparum FP2A inhibition | `{target}`, single protein | 4 | assay format = single protein format (from target) |
| PRT-00023 M. tuberculosis GyrA/GyrB inhibition [ATPase] | `{target}`, complex | 5 | protein complex format; unit typed `uM` stored `µM`; PRT-00009 left bare → flagged `needs_discriminator` |
| PRT-00024 M. abscessus growth inhibition | `{organism}` | 5 | nickname "Mabs MIC" saved at create |
| PRT-00025 M. abscessus growth inhibition [resazurin] | sibling family | 6 | PRT-00024 renamed to "[broth microdilution]" in the same save; former name kept as alias "Distinguished from PRT-00025" |
| PRT-00026 M. abscessus growth inhibition [luminescent reporter] | sibling family | 5 | both siblings listed by full name; edited readout + form switch → "Replace your readouts?" confirm renders over the dialog; "Keep mine" keeps the edit and the dialog |
| Hep G2 cytotoxicity | `{cell_line}` | 3 | single shipped form preselected |
| Microsomal stability [rat] | `{matrix}` | 3 | form sets microsome format → "Microsomal"; siblings [human]/[mouse] listed |
| Lipophilicity | no facts | 2 | LogD form preselected, pH condition applied |
| Firefly luciferase interference | `{discriminator}` | 3 | |
| Mouse pharmacokinetics | `{organism?}` | 4 | organism only reachable under More details (W7) |
| Combination (not saved) | `{subject?}` | — | bare "Combination" (W7) |

Admin: "Biofilm inhibition" created with "Start protocols like: Growth inhibition" → its three forms copied.

### Walk findings

- **W1 (bug):** after a create, reopening the dialog shows an empty Category yet the previous name preview and a false
  "PRT-… already has this exact name" error, until a category is picked. Reproduced twice.
- **W2 (cosmetic):** unit suggestions render as "µMConcentration" (no gap between unit and group).
- **W3 (chemistry, decision):** the shipped MIC form presets µM; CLSI reports MIC in µg/mL, medicinal chemistry often µM.
  Conventions differ, so by the design-general rule the form might preselect neither.
- **W4 (pre-existing):** ontology search ranks derivatives above the exact term: "HepG2-AhR-luc" above "Hep G2 cell",
  "Mus musculus musculus" above "Mus musculus". Easy to pick the wrong cell line or taxon.
- **W5 (UX):** conditions a form brings (LogD's pH) sit in collapsed More details; a chemist does not see them.
- **W6 (copy):** when the pattern requires `{discriminator}` (Detection interference, Receptor function) the helper text
  still says "Only needed when another protocol would get the same name" and the examples (resazurin, hypoxia) do not fit.
- **W7 (spec gap):** optional pattern slots (`{organism?}`, `{cell_line?}`, `{subject?}`) are only reachable under More
  details although they change the name; Pharmacokinetics names itself "Pharmacokinetics" unless the chemist finds
  Organism there.
