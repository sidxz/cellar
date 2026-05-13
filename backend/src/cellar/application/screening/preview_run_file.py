"""Preview / repreview use cases for the run-file importer.

Extracted from ``import_run_file.py`` so each use case class lives in
its own module. ``PreviewRunFile`` runs against a freshly uploaded file
with an auto-guessed mapping. ``RepreviewRunFile`` re-runs resolution
against an already-cached preview using a chemist-refined mapping —
they share the same DTO shape so the wizard panel can swap data in
place.

Both classes are re-exported from ``import_run_file`` so existing
callers and DI wiring keep working unchanged.
"""

from __future__ import annotations

import time
import uuid

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening.compound_ref_resolver import resolve_rows
from cellar.application.screening.import_plan import (
    ReadoutConflict,
    WellConflict,
    _scan_conflicts,
)
from cellar.application.screening.import_run_file_dtos import (
    AmbiguousCompoundDTO,
    PlatePreview,
    PreviewRunFileQuery,
    PreviewRunFileResult,
    RepreviewRunFileQuery,
)
from cellar.application.screening.import_run_file_mapper import (
    _build_batch_lookup,
    _build_compound_index,
    _build_guess_mapping,
    _summarize_plates,
    _to_ambiguous_dto,
)
from cellar.application.screening.import_run_file_preview_store import (
    PreviewStore,
    _guess_content_type,
    _StoredPreview,
)
from cellar.application.screening.import_run_file_validator import (
    _load_templates_by_format,
    _validate_controls_required,
)
from cellar.application.screening.long_format_normalizer import (
    NormalizedTable,
    ReadoutDefRef,
    infer_mapping,
    normalize,
)
from cellar.application.shared.parsers import TabularParseError, TabularParser
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.repository import BatchRepository
from cellar.domain.screening_assay.repository import (
    PlateTemplateRepository,
    ProtocolRepository,
    ReadoutDataRepository,
    RunRepository,
)
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)

# Hard cap from the plan: sync-only MVP.
_MAX_ROWS = 50_000


class PreviewRunFile:
    """Parse + suggest mapping + dry-resolve batches + scan conflicts."""

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
        batch_repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        preview_store: PreviewStore,
        protocol_repo: ProtocolRepository,
        plate_template_repo: PlateTemplateRepository,
        parser: TabularParser,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._molecule_repo = molecule_repo
        self._store = preview_store
        self._protocol_repo = protocol_repo
        self._plate_template_repo = plate_template_repo
        self._parser = parser

    async def __call__(
        self,
        input: PreviewRunFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRunFileResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            return await self._execute(input)

    async def _execute(
        self, input: PreviewRunFileQuery
    ) -> Result[PreviewRunFileResult, DomainError]:
        run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(input.run_id)))

        try:
            table = self._parser.parse(input.file_content, input.filename)
        except TabularParseError as exc:
            return Failure(ValidationError(f"File parse error: {exc}"))

        if table.row_count > _MAX_ROWS:
            return Failure(
                ValidationError(
                    f"File has {table.row_count} rows; sync import limit is {_MAX_ROWS}"
                )
            )

        # Load the protocol first so its readout-definition catalog can
        # feed into infer_mapping. Headers whose name matches a defined
        # readout (e.g. a Text readout named "Scientist") are then
        # suggested as role=readout / confidence=high with the def id
        # attached — no FE-side upgrade or auto-binding needed.
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            input.workspace_id, run.protocol_id
        )
        readout_def_refs: tuple[ReadoutDefRef, ...] = (
            tuple(
                ReadoutDefRef(
                    id=rd.id,
                    name=rd.name,
                    data_type=rd.data_type.value,
                )
                for rd in protocol.readout_definitions
            )
            if protocol is not None
            else ()
        )

        suggested = infer_mapping(table, readout_defs=readout_def_refs)
        guessed = _build_guess_mapping(suggested)

        plates: tuple[PlatePreview, ...] = ()
        matched_batches = 0
        unmatched_set: set[str] = set()
        unmatched_compound_set: frozenset[str] = frozenset()
        ambiguous_dto: tuple[AmbiguousCompoundDTO, ...] = ()
        row_conflict_strings: tuple[str, ...] = ()
        matched_compounds = 0
        validation_errors: list[str] = []
        will_create_plates = 0
        will_create_wells = 0
        will_create_readouts = 0
        well_conflicts: list[WellConflict] = []
        readout_conflicts: list[ReadoutConflict] = []

        if guessed is not None:
            normalized = normalize(table, guessed)
            if isinstance(normalized, Success):
                norm: NormalizedTable = normalized.unwrap()
                plates = _summarize_plates(norm.rows, norm.plate_formats)

                # Build both indexes, then run the resolver. Dry-run only
                # — no overrides at preview time.
                batch_index = await _build_batch_lookup(
                    norm.rows, input.workspace_id, self._batch_repo
                )
                compound_index = await _build_compound_index(
                    norm.rows,
                    input.workspace_id,
                    self._molecule_repo,
                    self._batch_repo,
                )
                resolutions = resolve_rows(
                    norm.rows,
                    batch_index=batch_index,
                    compound_index=compound_index,
                )
                # `matched_batches` is *distinct* batch refs that
                # resolved (matches the original `_resolve_batches`
                # contract — the wire format documents it as a count
                # of unique refs, not rows).
                matched_batches = len(batch_index)
                unmatched_set = set(resolutions.unmatched_batch_refs)
                unmatched_compound_set = resolutions.unmatched_compound_refs
                matched_compounds = resolutions.matched_compound_count
                ambiguous_dto = tuple(
                    _to_ambiguous_dto(a) for a in resolutions.ambiguous_compounds
                )
                row_conflict_strings = tuple(
                    f"{c.plate_name} {c.well_label}: {c.reason}" for c in resolutions.row_conflicts
                )

                if protocol is not None:
                    templates_by_format = await _load_templates_by_format(
                        protocol,
                        norm.plate_formats,
                        input.workspace_id,
                        self._plate_template_repo,
                    )
                    validation_errors = _validate_controls_required(
                        protocol, norm.plate_formats, templates_by_format
                    )

                    # Conflict scan against existing run state. Uses a
                    # best-guess readout-def binding (each readout column
                    # maps to a fresh UUID in the guessed mapping, which
                    # is fine for plate/well-level counts; the readout
                    # cell-level scan is approximate at preview time and
                    # gets re-run authoritatively at import time once the
                    # user has bound real readout-def IDs).
                    existing_readouts = await self._readout_data_repo.find_by_run(
                        input.workspace_id, run.id
                    )
                    plan = _scan_conflicts(
                        norm,
                        run,
                        existing_readouts,
                        templates_by_format,
                        resolutions=resolutions,
                    )
                    will_create_plates = plan.create_plate_count
                    will_create_wells = plan.create_well_count
                    will_create_readouts = plan.create_readout_count
                    well_conflicts = plan.well_conflicts
                    readout_conflicts = plan.readout_conflicts

        preview_id = uuid.uuid4()
        ttl = getattr(self._store, "ttl_seconds", 60.0)
        self._store.save(
            preview_id,
            _StoredPreview(
                workspace_id=input.workspace_id,
                run_id=input.run_id,
                table=table,
                raw_bytes=input.file_content,
                filename=input.filename,
                content_type=input.content_type or _guess_content_type(input.filename),
                expires_at=time.monotonic() + ttl,
            ),
        )

        sample = tuple({h: (r.get(h) or "") for h in table.headers} for r in table.rows[:5])

        return Success(
            PreviewRunFileResult(
                preview_id=preview_id,
                headers=tuple(table.headers),
                suggestions=suggested.suggestions,
                sample_rows=sample,
                plates=plates,
                matched_batches=matched_batches,
                unmatched_batches=tuple(sorted(unmatched_set)),
                total_rows=table.row_count,
                expires_in_seconds=int(ttl),
                validation_errors=tuple(validation_errors),
                will_create_plates=will_create_plates,
                will_create_wells=will_create_wells,
                will_create_readouts=will_create_readouts,
                will_skip_wells=tuple(well_conflicts),
                will_skip_readouts=tuple(readout_conflicts),
                matched_compounds=matched_compounds,
                unmatched_compound_refs=tuple(sorted(unmatched_compound_set)),
                ambiguous_compounds=ambiguous_dto,
                row_conflicts=row_conflict_strings,
            )
        )


class RepreviewRunFile:
    """Re-run resolution against a cached preview using a user mapping.

    The initial ``PreviewRunFile`` runs with an auto-guessed mapping —
    fine for showing the chemist what we *think* the columns are, but
    stale once they hand-correct any role assignment. This use case
    consumes the existing ``preview_id`` (without invalidating it),
    re-normalizes with the chemist-confirmed mapping, re-resolves
    batches + compounds, and returns the same DTO shape so the wizard
    can swap the panel data in place.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        run_repo: RunRepository,
        readout_data_repo: ReadoutDataRepository,
        batch_repo: BatchRepository,
        molecule_repo: MoleculeRepository,
        preview_store: PreviewStore,
        protocol_repo: ProtocolRepository,
        plate_template_repo: PlateTemplateRepository,
    ) -> None:
        self._uow = uow
        self._run_repo = run_repo
        self._readout_data_repo = readout_data_repo
        self._batch_repo = batch_repo
        self._molecule_repo = molecule_repo
        self._store = preview_store
        self._protocol_repo = protocol_repo
        self._plate_template_repo = plate_template_repo

    async def __call__(
        self,
        input: RepreviewRunFileQuery,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRunFileResult, DomainError]:
        require_editor(auth)

        async with self._uow:
            return await self._execute(input)

    async def _execute(
        self, input: RepreviewRunFileQuery
    ) -> Result[PreviewRunFileResult, DomainError]:
        cached = self._store.peek(input.preview_id)
        if cached is None:
            return Failure(NotFoundError("Preview", str(input.preview_id)))
        if cached.workspace_id != input.workspace_id or cached.run_id != input.run_id:
            return Failure(ValidationError("preview_id does not match this workspace + run"))

        run = await self._run_repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
        if run is None:
            return Failure(NotFoundError("Run", str(input.run_id)))

        protocol = await self._protocol_repo.find_by_id_in_workspace(
            input.workspace_id, run.protocol_id
        )
        readout_def_refs: tuple[ReadoutDefRef, ...] = (
            tuple(
                ReadoutDefRef(
                    id=rd.id,
                    name=rd.name,
                    data_type=rd.data_type.value,
                )
                for rd in protocol.readout_definitions
            )
            if protocol is not None
            else ()
        )

        # Re-run header inference for the response (so the wizard can
        # still display confidence badges) but use the user-supplied
        # mapping for normalization.
        suggested = infer_mapping(cached.table, readout_defs=readout_def_refs)

        normalized = normalize(cached.table, input.mapping)
        if isinstance(normalized, Failure):
            return normalized
        norm: NormalizedTable = normalized.unwrap()

        plates = _summarize_plates(norm.rows, norm.plate_formats)
        batch_index = await _build_batch_lookup(norm.rows, input.workspace_id, self._batch_repo)
        compound_index = await _build_compound_index(
            norm.rows,
            input.workspace_id,
            self._molecule_repo,
            self._batch_repo,
        )
        resolutions = resolve_rows(
            norm.rows, batch_index=batch_index, compound_index=compound_index
        )

        validation_errors: list[str] = []
        will_create_plates = 0
        will_create_wells = 0
        will_create_readouts = 0
        well_conflicts: list[WellConflict] = []
        readout_conflicts: list[ReadoutConflict] = []

        if protocol is not None:
            templates_by_format = await _load_templates_by_format(
                protocol,
                norm.plate_formats,
                input.workspace_id,
                self._plate_template_repo,
            )
            validation_errors = _validate_controls_required(
                protocol, norm.plate_formats, templates_by_format
            )
            existing_readouts = await self._readout_data_repo.find_by_run(
                input.workspace_id, run.id
            )
            plan = _scan_conflicts(
                norm,
                run,
                existing_readouts,
                templates_by_format,
                resolutions=resolutions,
            )
            will_create_plates = plan.create_plate_count
            will_create_wells = plan.create_well_count
            will_create_readouts = plan.create_readout_count
            well_conflicts = plan.well_conflicts
            readout_conflicts = plan.readout_conflicts

        ambiguous_dto = tuple(_to_ambiguous_dto(a) for a in resolutions.ambiguous_compounds)
        row_conflict_strings = tuple(
            f"{c.plate_name} {c.well_label}: {c.reason}" for c in resolutions.row_conflicts
        )

        sample = tuple(
            {h: (r.get(h) or "") for h in cached.table.headers} for r in cached.table.rows[:5]
        )
        ttl = getattr(self._store, "ttl_seconds", 60.0)

        return Success(
            PreviewRunFileResult(
                preview_id=input.preview_id,
                headers=tuple(cached.table.headers),
                suggestions=suggested.suggestions,
                sample_rows=sample,
                plates=plates,
                matched_batches=len(batch_index),
                unmatched_batches=tuple(sorted(resolutions.unmatched_batch_refs)),
                total_rows=cached.table.row_count,
                expires_in_seconds=int(ttl),
                validation_errors=tuple(validation_errors),
                will_create_plates=will_create_plates,
                will_create_wells=will_create_wells,
                will_create_readouts=will_create_readouts,
                will_skip_wells=tuple(well_conflicts),
                will_skip_readouts=tuple(readout_conflicts),
                matched_compounds=resolutions.matched_compound_count,
                unmatched_compound_refs=tuple(sorted(resolutions.unmatched_compound_refs)),
                ambiguous_compounds=ambiguous_dto,
                row_conflicts=row_conflict_strings,
            )
        )
