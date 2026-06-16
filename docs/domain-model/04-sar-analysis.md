# SAR Analysis Context

## Context Overview

Supporting subdomain that provides structural analysis capabilities — precomputed fingerprints for similarity searching and matched molecular pairs for structure-activity relationship analysis. This context consumes molecule data from Chemical Registration and produces derived analytical data.

**Depends on:** Chemical Registration (molecule structures)
**Depended on by:** UI/Application layer (search, visualization)

---

## Entities

### MolecularFingerprint

Precomputed bit-vector fingerprints for similarity searching. Derived data — regenerated when a molecule's structure changes. Not an aggregate root: created/deleted as a side effect of molecule registration and disclosure events.

| Property | Type | Description |
|----------|------|-------------|
| molecule_id | UUID | FK → Molecule (composite PK with fingerprint_type) |
| fingerprint_type | enum | morgan, rdkit, maccs, topological_torsion, atom_pair |
| radius | int? | For Morgan fingerprints (typically 2) |
| bits | int | Bit vector length (typically 2048) |
| fingerprint | binary | Bit vector |

**Lifecycle:**
- Created by `MoleculeRegistrationService` after molecule registration (for disclosed molecules)
- Created by `DisclosureService` after disclosure (for newly disclosed molecules)
- Deleted when source molecule becomes a tombstone (merge)
- Regenerated on structure correction

**Invariants:**
- Only exist for disclosed, non-tombstone molecules
- Multiple fingerprint types per molecule (one per type)

### MatchedMolecularPair

Precomputed pairs of molecules differing by a single structural transformation, with associated property deltas. Used for SAR analysis — understanding how specific structural changes affect biological activity.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| molecule_a_id | UUID | FK → Molecule |
| molecule_b_id | UUID | FK → Molecule |
| transformation | string | SMIRKS of the structural change (e.g., [*:1]F>>[*:1]Cl) |
| context | string | Common scaffold SMARTS |
| property_deltas | jsonb | {property: delta_value} for each measured property |

**Lifecycle:**
- Batch-computed by a domain service when new molecules are registered
- Invalidated/recomputed when molecules are merged or structures corrected
- Read-only from the application's perspective — no user-facing CRUD

**Invariants:**
- Both molecules must be active (non-tombstone) and disclosed
- `molecule_a_id < molecule_b_id` (canonical ordering to prevent duplicate pairs)

---

## Aggregates

### MarkushDefinition

A stored generic structure description defining a family of compounds through variable R-group positions on a core scaffold. Used for patent freedom-to-operate analysis, SAR scaffold definition, and library design. Building block for the future IP/Patent context.

**Aggregate Root:** MarkushDefinition

**Inside boundary:**
- `RGroupPosition[]` — variable positions on the core scaffold. Fully owned.
  - `RGroupSubstituent[]` — allowed substituents at each position. Owned by RGroupPosition.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Sentinel workspace |
| name | string | e.g., "Patent US12345678 Claim 1", "Kinase Scaffold Series A" |
| description | text? | Human-readable description of the chemical space |
| core_scaffold | string | SMARTS pattern for the fixed core structure |
| core_scaffold_molfile | text? | MDL MOL block with R-group labels |
| source_type | enum | `patent_claim`, `sar_scaffold`, `library_design`, `custom` |
| source_reference | string? | Patent number, publication, etc. |
| status | enum | `draft`, `active`, `archived` |
| estimated_library_size | int? | Approximate number of enumerated compounds |
| created_by | UUID | FK → User |
| created_at | timestamp | |
| updated_at | timestamp | |

#### Owned Entity: RGroupPosition

A variable position on the core scaffold (R1, R2, etc.).

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| markush_id | UUID | FK → parent MarkushDefinition |
| label | string | e.g., "R1", "R2", "R3" |
| attachment_point | int | Atom index on the core scaffold where this R-group attaches |
| is_required | bool | Must be substituted (vs. can be hydrogen) |
| display_order | int | |

#### Owned Entity: RGroupSubstituent

A specific substituent allowed at a given R-group position.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| r_group_position_id | UUID | FK → parent RGroupPosition |
| smarts | string | SMARTS pattern for this substituent |
| smiles | string? | Canonical SMILES (if concrete fragment) |
| name | string? | e.g., "methyl", "fluoro", "4-methylpiperazinyl" |
| nested_markush_id | UUID? | FK → MarkushDefinition (for nested R-groups) |
| display_order | int | |

#### Invariants

1. **Valid SMARTS:** `core_scaffold` must be syntactically valid SMARTS.
2. **At least one R-group:** Active definitions must have at least one RGroupPosition.
3. **At least one substituent per R-group:** Each RGroupPosition must define at least one RGroupSubstituent.
4. **Valid substituent SMARTS:** Each substituent's `smarts` must be valid.
5. **No circular nesting:** `nested_markush_id` reference chains must not form cycles.
6. **Nesting depth limit:** Configurable, default 3 levels.
7. **Attachment point validity:** Must reference a valid atom index in `core_scaffold`.
8. **R-group label uniqueness:** Labels unique within a MarkushDefinition.

#### State Transitions

```
draft ──[activate]──> active
active ──[archive]──> archived
archived ──[reactivate]──> active
```

#### Domain Events

| Event | Payload | When |
|-------|---------|------|
| `MarkushDefinitionCreated` | markush_id, name, source_type, r_group_count | New definition stored |
| `MarkushDefinitionActivated` | markush_id | Draft to active |
| `MarkushDefinitionArchived` | markush_id | Active to archived |
| `MarkushSearchExecuted` | markush_id, molecule_count_matched, search_duration_ms | Search completed |
| `MarkushEnumerationCompleted` | markush_id, enumeration_id, total_enumerated | Enumeration finished |
| `MarkushMatchesUpdated` | markush_id, new_matches_count, removed_matches_count | Matches recomputed |

---

### MarkushMatch

Records the result of a Markush search — which molecules match a given definition. Derived/computed data, same lifecycle pattern as MolecularFingerprint.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| markush_id | UUID | FK → MarkushDefinition |
| molecule_id | UUID | FK → Molecule |
| match_type | enum | `exact_core_match`, `substructure_match`, `enumerated_match` |
| r_group_assignments | jsonb | { "R1": "F", "R2": "OCH3", ... } |
| matched_at | timestamp | |

**Invariants:**
- Only disclosed, non-tombstone molecules (same as MolecularFingerprint)
- Unique on (markush_id, molecule_id)

---

### MarkushEnumeration

A stored batch enumeration of specific molecules from a Markush definition.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| markush_id | UUID | FK → MarkushDefinition |
| enumeration_type | enum | `full`, `sampled`, `representative` |
| sample_size | int? | For sampled enumerations |
| total_enumerated | int | Count of structures generated |
| status | enum | `pending`, `completed`, `failed` |
| started_at | timestamp | |
| completed_at | timestamp? | |
| initiated_by | UUID | FK → User |

**Invariants:**
- Full enumeration capped at configurable max (default: 100,000) to prevent runaway computation
- Larger spaces require `sampled` enumeration

---

## Async-job / read-model aggregates (Part 1b/2 additions)

Two aggregates were added when the SAR workbench moved its compute server-side.
They are **derived read models behind async jobs**, not registration state — they
hold no chemistry of record, only cached projections over already-registered
molecules. Both share an async-job lifecycle: `pending → running →
ready | failed | cancelled`.

### RGroupDecompositionRun

- **Purpose:** one R-group decomposition of a molecule set against a chosen core.
- **Identity / cache key:** `membership_hash` (fold over the scoped member set) +
  `core_hash` (canonical core SMILES). A `find_cached` lookup returns a prior run
  only when it is `READY`, so a `failed`/`cancelled` run is never reused and a
  re-request starts fresh.
- **State:** `status`, `rgroup_labels`, and `matched / unmatched / total` counts.
- **Read model:** `RGroupAssignment` rows (one per matched molecule, the R-group
  fragment SMILES per label) are what the `/decomposition/{run_id}/rows` and
  `/heatmap` endpoints page, sort, filter, and aggregate over.

### SarActivityProjection

- **Purpose:** project a single activity channel (a DR intercept or a raw readout,
  under a selection rule) onto a molecule set, so the table/heatmap can colour by
  potency without recomputing per render.
- **Identity / cache key:** `membership_hash` + `channel_hash` (the semantic
  channel fields). `READY`-only cache hits, same as the decomposition run.
- **State:** `status` + `ActivityScalar` values keyed by molecule id.
- **Consumed by:** the table activity column and the heatmap cell colouring,
  joined to the decomposition rows by molecule id at query time.

### Relationship to the existing aggregates

`MolecularFingerprint` and `MarkushDefinition` remain the SAR registration-side
aggregates. `RGroupDecompositionRun` and `SarActivityProjection` sit beside them
as compute artifacts layered on registered molecules — they can be dropped and
recomputed at any time without data loss.

---

## Domain Services

### MarkushSearchService

Orchestrates Markush searching against the molecule database.

**Spans:** MarkushDefinition, Molecule, MolecularFingerprint, MarkushMatch

**search():**
1. Parse MarkushDefinition into SMARTS queries (per R-group combination or hierarchical matching)
2. For simple definitions: RDKit SMARTS matching against all disclosed molecules
3. For complex definitions: fingerprint pre-screening to narrow candidates, then exact SMARTS
4. Record MarkushMatch results with R-group assignments
5. Emit `MarkushSearchExecuted`

### MarkushEnumerationService

Generates specific molecules from a Markush definition.

**Spans:** MarkushDefinition, Molecule (optional — checks if enumerated structures already exist)

**enumerate():**
1. Compute combinatorial product of all R-group substituents
2. For each combination: generate SMILES, canonicalize, compute InChIKey
3. Optionally check against existing molecules (flag known compounds)
4. Store results as MarkushEnumeration
5. Emit `MarkushEnumerationCompleted`

---

## Consistency Model

Derived data in this context follows two distinct consistency models:

### Synchronous (blocking registration/disclosure)

| Computation | Latency | Failure behavior |
|-------------|---------|------------------|
| **MolecularFingerprint** (all types) | ~10ms per molecule | Registration/disclosure **rolls back** if fingerprint computation fails. Fingerprints are essential for search — a molecule without fingerprints is unfindable. |

Fingerprint computation is fast (RDKit in-process) and must succeed for the molecule to be usable. It runs within the same transaction as registration/disclosure.

### Asynchronous (eventually consistent)

| Computation | Latency | Failure behavior |
|-------------|---------|------------------|
| **MatchedMolecularPair** batch computation | Minutes (scales with corpus size) | Registration succeeds regardless. MMP computation runs as a Temporal activity. Failed jobs are retried; missing MMPs don't block any workflow. |
| **MarkushMatch** checks against active definitions | Seconds to minutes | Registration succeeds regardless. Markush matching runs asynchronously. New matches appear when the async job completes. |
| **PredictedProperties** (logD, pKa, logS) | Seconds to minutes (depends on prediction service) | Registration succeeds regardless. Predictions arrive asynchronously and update the molecule's `predicted_properties` VO. |

Async computations are triggered by domain events and executed as Temporal activities. They are idempotent and retryable. The application layer should indicate to users when async computations are pending (e.g., "MMP analysis in progress").

---

## Triggered By (Domain Events)

| Event | Action |
|-------|--------|
| `MoleculeRegistered` (disclosed) | Compute fingerprints; batch-compute new MMPs against existing molecules |
| `MoleculeDisclosed` | Compute fingerprints; batch-compute new MMPs |
| `MoleculeMerged` | Delete source fingerprints; invalidate MMPs referencing source |
| `MoleculeStructureCorrected` | Recompute fingerprints; invalidate/recompute affected MMPs |
| `MoleculeRegistered` (disclosed) | Async: check against active MarkushDefinitions for new matches |
| `MoleculeDisclosed` | Async: check against active MarkushDefinitions for new matches |
| `MoleculeMerged` | Delete source MarkushMatch records (recompute for target on next search) |
