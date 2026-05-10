# Compound Ref Role for Run Import

**Date:** 2026-05-10
**Status:** Approved (auto-mode implementation)
**Related code:** `backend/src/chem_vault/application/screening/`, `frontend/src/features/screening-assay/components/run-import-wizard.tsx`

## Problem

Today the run-import wizard exposes one role for compound identification: **Batch Ref**. Scientists routinely upload spreadsheets that reference compounds by name / synonym / external ID rather than by batch number. Two latent issues result:

1. `_resolve_batch_ref` in `import_run_file.py:780-804` quietly does compound-name fallback via the `<name>-<seq>` regex — Batch Ref is doing two jobs and one of them is hidden.
2. Files that name a compound *without* a `-NN` suffix can't be imported at all; the chemist must hand-edit the spreadsheet to add batch numbers.

## Solution

Introduce a second role, **Compound Ref**, that resolves identifier-based references and derives a batch via inventory lookup. Narrow Batch Ref back to strict batch lookup. Surface ambiguity (one compound with N batches) explicitly in the preview UI as a per-molecule picker.

## Non-goals

- No new domain model. `Well.batch_id` and `ReadoutData.molecule_id`/`batch_id` are unchanged. Compound Ref is purely an import-time concept.
- No persisted disambiguation. User picks live in the import command, not in saved templates — choices are run-specific, not pattern-specific.
- No cross-identifier collision detection. The `uq_ws_identifier` unique constraint on `(workspace_id, identifier)` guarantees one identifier string maps to ≤1 molecule per workspace.

## Architecture

### Layer placement

- New module: `backend/src/chem_vault/application/screening/compound_ref_resolver.py` — pure functions, no I/O. Mirrors how `import_plan.py` was extracted from `import_run_file.py`.
- Async loaders that touch repositories (`_build_compound_index`, `_build_batch_lookup`) stay in `import_run_file.py` next to existing `_resolve_batches`.
- `_scan_conflicts` in `import_plan.py` accepts a pre-computed `Resolutions` object instead of re-resolving from `row.batch_ref`.

### Domain & data shape

**Normalizer (`long_format_normalizer.py`):**

```python
Role = Literal["well", "plate_name", "concentration", "batch_ref",
               "compound_ref", "readout"]

_SYNONYMS["compound_ref"] = frozenset(_norm(x) for x in (
    "compound", "compound name", "compound id", "molecule",
    "molecule name", "molecule id", "synonym", "external id",
    "registration number", "reg number", "cv id",
))
# Removed from batch_ref synonyms: "compound id", "sample id"
```

```python
@dataclass(frozen=True)
class ColumnMapping:
    well: str
    plate_name: str | None = None
    concentration: str | None = None
    batch_ref: str | None = None
    compound_ref: str | None = None       # new
    readout_columns: tuple[ReadoutColumn, ...] = ()

@dataclass(frozen=True)
class LongFormatRow:
    plate_name: str
    well: WellPosition
    batch_ref: str | None
    compound_ref: str | None              # new
    concentration: float | None
    readouts: dict[uuid.UUID, float | str]
```

### Resolver module (`compound_ref_resolver.py`)

```python
@dataclass(frozen=True)
class BatchSummary:
    batch_id: uuid.UUID
    batch_number: str
    salt_form: str | None
    purity: float | None
    created_at: datetime

@dataclass(frozen=True)
class _Candidate:
    molecule_id: uuid.UUID
    molecule_name: str
    batches: tuple[BatchSummary, ...]

@dataclass(frozen=True)
class RowResolution:
    batch_id: uuid.UUID | None
    molecule_id: uuid.UUID | None
    source: Literal["batch_ref", "compound_ref", "override"] | None
    error: ResolveError | None

@dataclass(frozen=True)
class AmbiguousCompound:
    compound_ref: str            # the input string
    molecule_id: uuid.UUID
    molecule_name: str
    batch_options: tuple[BatchSummary, ...]
    affected_row_count: int

@dataclass(frozen=True)
class RowConflict:
    plate_name: str
    well_label: str
    batch_ref: str
    compound_ref: str
    reason: str    # "Batch Ref points to molecule X; Compound Ref points to molecule Y"

@dataclass(frozen=True)
class Resolutions:
    per_row: tuple[RowResolution, ...]
    unmatched_batch_refs: frozenset[str]
    unmatched_compound_refs: frozenset[str]
    ambiguous_compounds: tuple[AmbiguousCompound, ...]
    row_conflicts: tuple[RowConflict, ...]


def resolve_rows(
    rows: Sequence[LongFormatRow],
    *,
    batch_index: Mapping[str, tuple[uuid.UUID, uuid.UUID]],
    compound_index: Mapping[str, _Candidate],
    overrides: Mapping[uuid.UUID, uuid.UUID] = {},
) -> Resolutions: ...
```

### Per-row precedence

Computed in `resolve_rows` for each `LongFormatRow`:

| `batch_ref` set? | `compound_ref` set? | Behavior |
|---|---|---|
| Yes (resolves) | No | Use batch (`source="batch_ref"`). |
| Yes (resolves) | Yes (resolves to same molecule) | Use batch (`source="batch_ref"`). |
| Yes (resolves) | Yes (resolves to different molecule) | Row conflict; row dropped from plan. |
| Yes (unmatched) | * | `unmatched_batch_refs` += value; row dropped if SAMPLE. |
| No | Yes, override exists for that molecule | Use override (`source="override"`). |
| No | Yes, exactly 1 batch in inventory | Auto-pick (`source="compound_ref"`). |
| No | Yes, N>1 batches | `ambiguous_compounds` entry; row dropped this pass. |
| No | Yes, identifier matches no molecule | `unmatched_compound_refs` += value. |
| No | No | Same as today — sample rows dropped, control rows kept. |

### Async loaders (in `import_run_file.py`)

```python
async def _build_compound_index(
    rows: Iterable[LongFormatRow],
    workspace_id: uuid.UUID,
    molecule_repo: MoleculeRepository,
    batch_repo: BatchRepository,
) -> dict[str, _Candidate]:
    """One molecule_repo.find_by_identifier per distinct compound_ref;
    one batch_repo.find_by_molecule per distinct molecule_id. Both
    workspace-scoped. Per-distinct-value caching."""
```

`_build_batch_lookup` is unchanged in shape; it now resolves `find_by_batch_number` only.

### Wire format

**Preview response (`PreviewRunFileResult`):**

```python
matched_compounds: int = 0
unmatched_compound_refs: tuple[str, ...] = ()
ambiguous_compounds: tuple[AmbiguousCompoundDTO, ...] = ()
row_conflicts: tuple[str, ...] = ()    # human-readable "Plate-1 A12: ..."
```

**Import command:**

```python
@dataclass(frozen=True, kw_only=True)
class ImportRunFileCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    preview_id: uuid.UUID
    mapping: ColumnMapping
    compound_batch_overrides: dict[uuid.UUID, uuid.UUID] = {}
```

### Frontend wizard changes

`run-import-wizard.tsx`:

- Add `{ value: "compound_ref", label: "Compound Ref" }` to `ROLE_OPTIONS` (between Batch Ref and Readout).
- Add `compound_ref` to the unique-roles set on line 272 — only one column may carry it.
- Preview step: new **Disambiguate compounds** panel renders when `ambiguous_compounds.length > 0`. One row per ambiguous molecule with a `<Select>` of batches (label: `batch_number — salt_form — created_at — purity %`). "Apply to N rows" hint. Continue disabled until all resolved.
- Disambiguation picks held in component state, passed as `compound_batch_overrides` in the import POST.
- `unmatched_compound_refs` rendered in the existing red-list pattern, alongside `unmatched_batches`.
- `row_conflicts` rendered next to `pick_list_violations`.
- Run-import-template DTO: add `mapping.compound_ref`. `applyTemplateToDraft` (line 104) handles it.

### Cleanup (consequences of "drop the fallback")

- Remove `_BATCH_REF_PATTERN` and the `<name>-<seq>` branch from `_resolve_batch_ref`.
- Remove `"compound id"` and `"sample id"` from `batch_ref` synonyms.
- `_resolve_batch_ref` becomes a thin wrapper over `find_by_batch_number`; consider inlining and dropping the helper.

## Error handling

| Surface | Trigger | Behavior |
|---|---|---|
| `unmatched_batch_refs` | Batch Ref values not in inventory | Existing red-list pattern. Sample rows dropped silently (today's behavior preserved). |
| `unmatched_compound_refs` | Compound Ref identifiers no molecule matches | New red-list section. Sample rows dropped. |
| `ambiguous_compounds` | Compound resolves to N>1 batches | Disambiguation panel. Continue disabled. Backend re-validates: still ambiguous after overrides → `ValidationError`. |
| `row_conflicts` | Both refs set, different molecules | Hard error list. Continue disabled. Backend `ValidationError` (parity with pick-list violations). |

## Testing

| File | Type | Coverage |
|---|---|---|
| `tests/unit/application/screening/test_compound_ref_resolver.py` | new | Pure-function suite. Auto-pick, ambiguity, override application, batch_ref-wins, both-agree, both-disagree, both-empty + sample dropped, both-empty + control kept. |
| `tests/unit/application/screening/test_long_format_normalizer.py` | extend | Synonym detection for compound_ref; ColumnMapping with both refs; both absent. |
| `tests/integration/screening/test_import_run_file_compound_ref.py` | new | E2E: preview surfaces ambiguity DTO; import without overrides → ValidationError; import with overrides → success and chosen batch persisted. |
| `tests/integration/screening/test_import_run_file.py` | audit | Existing tests touching `_resolve_batch_ref` may need re-mapping to compound_ref or to use real batch numbers. |

## Migration

- Saved run-import templates: `mapping.compound_ref` missing on existing rows → treated as None. No data migration.
- Templates that resolved via the dropped `<name>-<seq>` Batch Ref fallback will produce `unmatched_batches` on next use → chemist re-maps the column to Compound Ref. This is the explicit consequence accepted in the design.

## Open questions

None.
