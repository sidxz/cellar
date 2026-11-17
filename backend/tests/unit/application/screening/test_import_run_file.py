"""Unit tests for ImportRunFile + PreviewRunFile use cases."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.compound_ref_resolver import LOTS_UNMATCHED_NOTE
from cellar.application.screening.import_run_file import (
    ImportRunFile,
    ImportRunFileCommand,
    InMemoryPreviewStore,
    PreviewRunFile,
    PreviewRunFileQuery,
    RepreviewRunFile,
    RepreviewRunFileQuery,
)
from cellar.application.screening.import_run_file_validator import _swapped_controls
from cellar.application.screening.long_format_normalizer import (
    CALCULATED_BY_SOURCE,
    ColumnMapping,
    NormalizedTable,
    ReadoutColumn,
    infer_mapping,
    normalize,
)
from cellar.domain.screening_assay.enums import (
    HolderKind,
    PosControlSignal,
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from cellar.domain.screening_assay.plate_template import PlateTemplate
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.run import Plate, Run
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.infrastructure.parsers.tabular_file import TabularFileParser, parse_tabular

# Real lab export, not in the repo: set NADD_FIXTURE=/path/to/file.xlsx to run these tests.
_NADD_FIXTURE = os.environ.get("NADD_FIXTURE", "")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


@dataclass
class FakeBatch:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    molecule_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class _FakeRegNumber:
    value: str = "CV-00001"


@dataclass
class FakeMolecule:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Test Molecule"
    registration_number: _FakeRegNumber = field(
        default_factory=lambda: _FakeRegNumber(value="CV-00001")
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _make_run(workspace_id: uuid.UUID, *, with_wells: bool = False, locked: bool = False) -> Run:
    return Run(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 4, 20),
        operator=uuid.uuid4(),
        is_locked=locked,
    )


def _with_cassette(run: Run) -> Run:
    """Give ``run`` a holder that is not a plate."""
    run.plates = [
        Plate(
            run_id=run.id,
            plate_number=1,
            holder_kind=HolderKind.CASSETTE,
            holder_rows=1,
            holder_columns=3,
        )
    ]
    return run


NOT_A_PLATE = "This run's holder is not a plate, so plate imports are not available for it."


def _make_protocol(
    workspace_id: uuid.UUID,
    readout_names: list[str],
    *,
    normalization: ReadoutNormalization = ReadoutNormalization.NONE,
    control_layouts: dict[str, uuid.UUID] | None = None,
) -> Protocol:
    norm_set = (
        frozenset({normalization}) if normalization != ReadoutNormalization.NONE else frozenset()
    )
    rds = [
        ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name=n,
            data_type=ReadoutDataType.NUMERIC,
            normalizations=norm_set,
        )
        for n in readout_names
    ]
    return Protocol(
        workspace_id=workspace_id,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        status=ProtocolStatus.ACTIVE,
        readout_definitions=rds,
        control_layouts=control_layouts,
    )


def _make_plate_template(
    workspace_id: uuid.UUID,
    *,
    fmt: PlateFormat = PlateFormat.F384,
    template_map: dict[str, str] | None = None,
) -> PlateTemplate:
    return PlateTemplate(
        workspace_id=workspace_id,
        name="Test Layout",
        format=fmt,
        template_map=template_map or {},
        created_by=uuid.uuid4(),
    )


def _make_plate_template_repo(
    templates_by_id: dict[uuid.UUID, PlateTemplate] | None = None,
) -> AsyncMock:
    repo = AsyncMock()
    by_id = templates_by_id or {}

    async def _find(_ws, tmpl_id):
        return by_id.get(tmpl_id)

    repo.find_by_id_in_workspace = _find
    return repo


def _build_preview_uc(
    *,
    run: Run | None,
    batches_by_ref: dict[str, FakeBatch] | None = None,
    molecules_by_synonym: dict[str, FakeMolecule] | None = None,
    store: InMemoryPreviewStore | None = None,
    protocol: Protocol | None = None,
    plate_templates: dict[uuid.UUID, PlateTemplate] | None = None,
    existing_readouts: list | None = None,
    has_wellless_rows: bool = False,
) -> tuple[PreviewRunFile, InMemoryPreviewStore]:
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)

    batch_repo = AsyncMock()

    async def _find(_ws, ref):
        return (batches_by_ref or {}).get(ref)

    batch_repo.find_by_batch_number = _find
    # resolve_batch_ref falls back to find_by_external_identifier; return None
    # for refs not in batches_by_ref so unmatched refs stay unmatched.
    batch_repo.find_by_external_identifier = AsyncMock(return_value=None)

    molecule_repo = AsyncMock()

    async def _find_mol(_ws, ident):
        return (molecules_by_synonym or {}).get(ident)

    molecule_repo.find_by_identifier = _find_mol

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run = AsyncMock(return_value=existing_readouts or [])
    readout_data_repo.has_wellless_rows = AsyncMock(return_value=has_wellless_rows)

    store = store or InMemoryPreviewStore(ttl_seconds=60)
    return (
        PreviewRunFile(
            uow=FakeUoW(),
            run_repo=run_repo,
            readout_data_repo=readout_data_repo,
            batch_repo=batch_repo,
            molecule_repo=molecule_repo,
            preview_store=store,
            protocol_repo=protocol_repo,
            plate_template_repo=_make_plate_template_repo(plate_templates),
            parser=TabularFileParser(),
        ),
        store,
    )


def _build_import_uc(
    *,
    run: Run,
    protocol: Protocol,
    batches_by_ref: dict[str, FakeBatch],
    store: InMemoryPreviewStore,
    save_bulk: list | None = None,
    molecules_by_synonym: dict[str, FakeMolecule] | None = None,
    plate_templates: dict[uuid.UUID, PlateTemplate] | None = None,
    existing_readouts: list | None = None,
    upload_attachment=None,
    plate_repo=None,
    plate_visibility=None,
    has_wellless_rows: bool = False,
) -> tuple[ImportRunFile, FakeUoW, AsyncMock]:
    uow = FakeUoW()

    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    run_repo.save = AsyncMock()

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run = AsyncMock(return_value=existing_readouts or [])
    readout_data_repo.has_wellless_rows = AsyncMock(return_value=has_wellless_rows)
    saved_list = save_bulk if save_bulk is not None else []

    async def _save_bulk(entities):
        saved_list.extend(entities)

    readout_data_repo.save_bulk = _save_bulk

    batch_repo = AsyncMock()

    async def _find(_ws, ref):
        return batches_by_ref.get(ref)

    batch_repo.find_by_batch_number = _find
    # resolve_batch_ref falls back to find_by_external_identifier; return None
    # for refs not in batches_by_ref so unmatched refs stay unmatched.
    batch_repo.find_by_external_identifier = AsyncMock(return_value=None)

    molecule_repo = AsyncMock()

    async def _find_mol(_ws, ident):
        return (molecules_by_synonym or {}).get(ident)

    molecule_repo.find_by_identifier = _find_mol

    if upload_attachment is None:
        upload_attachment = AsyncMock()
        # Return a Success result with a fake attachment.
        from returns.result import Success as _Success

        class _FakeAttachment:
            id = uuid.uuid4()

        async def _no_op(*_args, **_kw):
            return _Success(_FakeAttachment())

        upload_attachment.side_effect = _no_op

    uc = ImportRunFile(
        uow=uow,
        run_repo=run_repo,
        protocol_repo=protocol_repo,
        readout_data_repo=readout_data_repo,
        batch_repo=batch_repo,
        molecule_repo=molecule_repo,
        preview_store=store,
        plate_template_repo=_make_plate_template_repo(plate_templates),
        upload_attachment=upload_attachment,
        plate_repo=plate_repo,
        plate_visibility=plate_visibility,
    )
    return uc, uow, run_repo


# ---------------------------------------------------------------------------
# PreviewRunFile
# ---------------------------------------------------------------------------


class TestPreviewRunFile:
    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, _ = _build_preview_uc(run=None)
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                file_content=b"a,b\n1,2\n",
                filename="x.csv",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_simple_csv_returns_preview(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        batch = FakeBatch()
        uc, store = _build_preview_uc(run=run, batches_by_ref={"LG-1": batch})

        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"P1,A1,100,LG-1,0.5\n"
            b"P1,A2,50,LG-1,0.4\n"
            b"P1,A3,,,0.9\n"  # blank
            b"P1,,,,0.1\n"  # no well -> dropped at normalization, counted in rows_skipped
        )
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="x.csv",
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        preview = result.unwrap()
        assert preview.total_rows == 4
        assert preview.rows_skipped == 1
        assert len(preview.plates) == 1
        plate = preview.plates[0]
        assert plate.plate_name == "P1"
        assert plate.sample_count == 2
        assert plate.blank_count == 1
        assert preview.matched_batch_count == 1
        assert preview.unmatched_batch_refs == ()
        # Cached for follow-up import
        assert preview.preview_id in store._items

    @pytest.mark.asyncio
    async def test_columns_the_source_calculated_from_a_readout_default_to_ignore(
        self,
    ) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(
            auth.workspace_id, ["raw AU"], normalization=ReadoutNormalization.PERCENT_INHIBITION
        )
        uc, _ = _build_preview_uc(run=run, protocol=protocol)
        csv = b"Plate,Well,raw AU (AU),% inhibition (%)\nP1,A1,0.42,45\n"
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="x.csv",
            ),
            auth=auth,
        )
        s = {x.header: x for x in result.unwrap().suggestions}
        assert s["raw AU (AU)"].readout_definition_id == protocol.readout_definitions[0].id
        assert (s["% inhibition (%)"].role, s["% inhibition (%)"].reason) == (
            None,
            CALCULATED_BY_SOURCE,
        )

    @pytest.mark.asyncio
    async def test_unmatched_batches_listed(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _ = _build_preview_uc(run=run, batches_by_ref={})
        csv = b"Plate Name,Well,Batch,Raw Data\nP1,A1,LG-MISSING,0.5\n"
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="x.csv",
            ),
            auth=auth,
        )
        preview = result.unwrap()
        assert preview.unmatched_batch_refs == ("LG-MISSING",)
        assert preview.matched_batch_count == 0

    @pytest.mark.asyncio
    async def test_preview_onto_a_wellless_run_is_refused(self) -> None:
        """A run already holding summary rows has no plates to preview into."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        uc, _ = _build_preview_uc(run=run, has_wellless_rows=True)

        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=b"Plate Name,Well,Raw Data\nP1,A1,0.5\n",
                filename="x.csv",
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        error = result.failure()
        assert isinstance(error, ConflictError)
        assert "well-less summary results" in str(error)

    @pytest.mark.asyncio
    async def test_preview_onto_a_run_whose_holder_is_not_a_plate_is_refused(self) -> None:
        auth = FakeAuth()
        run = _with_cassette(_make_run(auth.workspace_id))
        uc, _ = _build_preview_uc(run=run)

        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=b"Plate Name,Well,Raw Data\nP1,A1,0.5\n",
                filename="x.csv",
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        assert str(result.failure()) == NOT_A_PLATE


# ---------------------------------------------------------------------------
# ImportRunFile
# ---------------------------------------------------------------------------


def _seed_preview(
    store: InMemoryPreviewStore,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    file_content: bytes,
    filename: str,
) -> uuid.UUID:
    """Helper: parse a file directly and stash it under a fresh preview_id."""
    preview_id = uuid.uuid4()
    store.save(preview_id, _stored(workspace_id, run_id, file_content, filename))
    return preview_id


def _stored(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    file_content: bytes = b"Well,Raw\nA1,0.5\n",
    filename: str = "x.csv",
):
    from cellar.application.screening.import_run_file import _StoredPreview

    return _StoredPreview(
        workspace_id=workspace_id,
        run_id=run_id,
        table=parse_tabular(file_content, filename),
        raw_bytes=file_content,
        filename=filename,
        content_type="text/csv",
    )


class TestInMemoryPreviewStore:
    """A chemist can spend half an hour on a 60-column mapping."""

    def _store(self, **kw):
        now = [0.0]
        return InMemoryPreviewStore(clock=lambda: now[0], **kw), now

    def test_a_preview_lives_thirty_minutes_by_default(self) -> None:
        store, now = self._store()
        store.save(key := uuid.uuid4(), _stored(uuid.uuid4(), uuid.uuid4()))
        now[0] = 29 * 60
        assert store.peek(key) is not None
        assert store.ttl_seconds == 30 * 60

    def test_every_use_restarts_the_clock(self) -> None:
        store, now = self._store()
        store.save(key := uuid.uuid4(), _stored(uuid.uuid4(), uuid.uuid4()))
        for minute in (25, 50, 75):
            now[0] = minute * 60
            assert store.peek(key) is not None, minute
        now[0] = 106 * 60
        assert store.peek(key) is None

    def test_the_least_recently_used_preview_goes_past_the_cap(self) -> None:
        store, now = self._store(max_items=2)
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        store.save(a, _stored(uuid.uuid4(), uuid.uuid4()))
        now[0] = 1
        store.save(b, _stored(uuid.uuid4(), uuid.uuid4()))
        now[0] = 2
        store.peek(a)
        store.save(c, _stored(uuid.uuid4(), uuid.uuid4()))
        assert store.peek(b) is None
        assert store.peek(a) is not None and store.peek(c) is not None


class TestImportRunFile:
    @pytest.mark.asyncio
    async def test_happy_path_simple_csv(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"P1,A1,100,LG-1,0.5\n"
            b"P1,A2,50,LG-1,0.4\n"
            b"P1,A3,,,0.9\n"
            b"P1,,,,0.1\n"  # no well -> dropped at normalization, counted in rows_skipped
        )
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )

        saved: list = []
        uc, uow, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
        )

        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()
        # Same vocabulary as the preview: total_rows is the RAW file row count,
        # rows_skipped the rows dropped at normalization (no parseable well).
        assert out.total_rows == 4
        assert out.rows_skipped == 1
        assert out.plates_created == 1
        # Sample wells (A1, A2) + blank (A3) — all 3 wells created
        assert out.wells_created == 3
        # Readouts written for all wells with values, including the blank
        # (control wells need raw values for plate normalization).
        assert out.values_inserted == 3
        assert len(saved) == 3
        # Protocol has no control layout + normalization is NONE → blank row
        # falls through to SAMPLE; counted as unclassified rather than typed.
        assert out.controls_unclassified == 1
        assert out.controls_from_template == 0
        # Non-sample readouts have None molecule/batch ids
        non_sample = [r for r in saved if r.molecule_id is None]
        assert len(non_sample) == 1
        assert non_sample[0].batch_id is None
        assert uow.committed
        # Run aggregate state
        assert len(run.plates) == 1
        assert len(run.wells) == 3

    @pytest.mark.asyncio
    async def test_import_onto_a_wellless_run_is_refused(self) -> None:
        """Plate-shaped import must not land on a run holding summary rows."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Plate Name,Well,Raw Data\nP1,A1,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )

        saved: list = []
        uc, uow, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={},
            store=store,
            save_bulk=saved,
            has_wellless_rows=True,
        )

        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate Name",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        assert saved == []
        assert not uow.committed
        assert run.plates == []

    @pytest.mark.asyncio
    async def test_import_onto_a_run_whose_holder_is_not_a_plate_is_refused(self) -> None:
        auth = FakeAuth()
        run = _with_cassette(_make_run(auth.workspace_id))
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Plate Name,Well,Raw Data\nP1,A1,0.5\n",
            filename="x.csv",
        )
        saved: list = []
        uc, uow, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={}, store=store, save_bulk=saved
        )

        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate Name",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert str(result.failure()) == NOT_A_PLATE
        assert saved == []
        assert not uow.committed
        assert len(run.plates) == 1 and run.wells == []

    @pytest.mark.asyncio
    async def test_mapping_onto_a_calculated_readout_is_refused(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        protocol.readout_definitions.append(
            ReadoutDefinition(
                protocol_id=protocol.id,
                name="Percent Inhibition",
                data_type=ReadoutDataType.NUMERIC,
                is_calculated=True,
                calculation_formula="100 - [Raw Data]",
            )
        )
        calc_id = protocol.readout_definitions[-1].id

        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Batch,Percent Inhibition\nA1,LG-1,42\n",
            filename="x.csv",
        )

        saved: list = []
        uc, uow, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": FakeBatch()},
            store=store,
            save_bulk=saved,
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                batch_ref="Batch",
                readout_columns=(
                    ReadoutColumn(header="Percent Inhibition", readout_definition_id=calc_id),
                ),
            ),
        )

        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure), result
        message = str(result.failure())
        assert "Percent Inhibition" in message
        assert "calculated" in message
        assert saved == []
        assert not uow.committed

    @pytest.mark.asyncio
    async def test_preview_id_is_single_use(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Batch,Raw Data\nA1,LG-1,0.5\n",
            filename="x.csv",
        )

        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        first = await uc(cmd, auth=auth)
        assert isinstance(first, Success)

        # Second call with same preview_id must fail — NotFoundError.
        # Need a fresh run aggregate (the previous one now has wells from first call,
        # so the conflict guard would trigger first); use a different run_id.
        run2 = _make_run(auth.workspace_id)
        uc2, _, _ = _build_import_uc(
            run=run2, protocol=protocol, batches_by_ref={"LG-1": batch}, store=store
        )
        cmd2 = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run2.id,
            preview_id=preview_id,
            mapping=cmd.mapping,
        )
        second = await uc2(cmd2, auth=auth)
        assert isinstance(second, Failure)
        assert isinstance(second.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_locked_run_refused(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id, locked=True)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Batch,Raw Data\nA1,LG-1,0.5\n",
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(run=run, protocol=protocol, batches_by_ref={}, store=store)
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)

    @pytest.mark.asyncio
    async def test_readout_def_not_in_protocol_rejected(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Raw Data\nA1,0.5\n",
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(run=run, protocol=protocol, batches_by_ref={}, store=store)
        wrong_rd = uuid.uuid4()  # not in protocol
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=wrong_rd),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unmatched_batches_skipped_and_reported(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=(
                b"Well,Batch,Raw Data\nA1,LG-MISSING,0.5\nA2,,0.9\n"  # blank — no batch
            ),
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(run=run, protocol=protocol, batches_by_ref={}, store=store)
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        out = result.unwrap()
        assert out.unmatched_batch_refs == ["LG-MISSING"]
        # A1 was skipped (unmatched), A2 is a blank — only one well created.
        assert out.wells_created == 1
        # The blank well still gets its readout written (non-sample readouts
        # have None molecule/batch and feed plate normalization).
        assert out.values_inserted == 1

    @pytest.mark.asyncio
    async def test_normalization_without_control_layout_fails(self) -> None:
        """Percent-inhibition protocol without a configured layout must block."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
        )
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Batch,Raw Data\nA1,LG-1,0.5\n",
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={"LG-1": batch}, store=store
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "Control Layout" in str(err)

    @pytest.mark.asyncio
    async def test_template_classifies_positive_control_well(self) -> None:
        """A configured template overrides the SAMPLE default for blank rows."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        # Plate template: A1 is positive_control, A2 is negative_control.
        tmpl = _make_plate_template(
            auth.workspace_id,
            fmt=PlateFormat.F96,
            template_map={"A1": "positive_control", "A2": "negative_control"},
        )
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
            control_layouts={PlateFormat.F96.value: tmpl.id},
        )
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            # A1 (pos ctrl, no batch), A2 (neg ctrl, no batch), A3 (sample),
            # H12 corner cell to force 96-well plate-format inference.
            file_content=(b"Well,Batch,Raw Data\nA1,,0.07\nA2,,0.95\nA3,LG-1,0.5\nH12,LG-1,0.5\n"),
            filename="x.csv",
        )
        batch = FakeBatch()
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.controls_from_template == 2
        assert out.controls_unclassified == 0
        # Verify wells got the right types from the template.
        wells_by_pos = {(w.row, w.column): w for w in run.wells}
        assert wells_by_pos[("A", 1)].well_type == WellType.POSITIVE_CONTROL
        assert wells_by_pos[("A", 2)].well_type == WellType.NEGATIVE_CONTROL
        assert wells_by_pos[("A", 3)].well_type == WellType.SAMPLE

    @pytest.mark.asyncio
    async def test_template_wins_over_row_concentration(self) -> None:
        """A control well with a concentration value MUST stay classified by
        the template — the template is the canonical source of well type.

        Regression: prior logic forced WellType.SAMPLE whenever the row had
        a concentration or batch_ref, skipping the template and silently
        breaking %-Inhibition normalization (no POS controls -> no curves).
        """
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        # A1 = positive_control per template. The file lists a concentration
        # for A1 (e.g. the inhibitor's fixed dose) — must NOT mis-classify.
        tmpl = _make_plate_template(
            auth.workspace_id,
            fmt=PlateFormat.F96,
            template_map={"A1": "positive_control", "A2": "negative_control"},
        )
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
            control_layouts={PlateFormat.F96.value: tmpl.id},
        )
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=(
                b"Well,Concentration,Batch,Raw Data\n"
                b"A1,100,,0.07\n"  # POS control with inhibitor concentration
                b"A2,,,0.95\n"  # NEG control, blank conc
                b"A3,33.3,LG-1,0.5\n"  # SAMPLE
                b"H12,33.3,LG-1,0.5\n"  # corner -> 96-well inferred
            ),
            filename="x.csv",
        )
        batch = FakeBatch()
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    concentration="Concentration",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        wells_by_pos = {(w.row, w.column): w for w in run.wells}
        # Critical assertions — template wins over row data.
        assert wells_by_pos[("A", 1)].well_type == WellType.POSITIVE_CONTROL
        assert wells_by_pos[("A", 2)].well_type == WellType.NEGATIVE_CONTROL
        assert wells_by_pos[("A", 3)].well_type == WellType.SAMPLE
        # POS well preserves its dose (didn't get dropped).
        assert wells_by_pos[("A", 1)].dose == 100

    @pytest.mark.asyncio
    async def test_control_well_with_unresolved_batch_not_dropped(self) -> None:
        """A control well classified by template stays even if its row has an
        unresolved batch_ref. Only SAMPLE wells with unresolved batches skip.
        """
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        tmpl = _make_plate_template(
            auth.workspace_id,
            fmt=PlateFormat.F96,
            template_map={"A1": "positive_control"},
        )
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
            control_layouts={PlateFormat.F96.value: tmpl.id},
        )
        # Need at least one well that's NEGATIVE_CONTROL for normalization
        # not to fail at calc time. Add A2 with NEG.
        tmpl.template_map["A2"] = "negative_control"
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=(
                b"Well,Batch,Raw Data\n"
                b"A1,LG-MISSING,0.07\n"  # POS w/ unresolved batch — keep
                b"A2,,0.95\n"  # NEG, blank
                b"A3,LG-MISSING,0.5\n"  # SAMPLE w/ unresolved — skip
                b"H12,,0.5\n"  # corner — 96-well
            ),
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={},
            store=store,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        wells_by_pos = {(w.row, w.column): w for w in run.wells}
        # POS control persisted with batch_id=None (unresolved kept anyway).
        assert ("A", 1) in wells_by_pos
        assert wells_by_pos[("A", 1)].well_type == WellType.POSITIVE_CONTROL
        assert wells_by_pos[("A", 1)].batch_id is None
        # NEG control persisted.
        assert ("A", 2) in wells_by_pos
        # SAMPLE A3 with unresolved batch was skipped.
        assert ("A", 3) not in wells_by_pos
        # Corner H12 is a SAMPLE with no batch (template silent for H12) — kept.
        assert ("H", 12) in wells_by_pos


# ---------------------------------------------------------------------------
# NadD fixture end-to-end
# ---------------------------------------------------------------------------


class TestNadDFixtureRoundtrip:
    @pytest.fixture
    def fixture_bytes(self) -> bytes:
        try:
            with open(_NADD_FIXTURE, "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            pytest.skip(f"NadD fixture missing (NADD_FIXTURE={_NADD_FIXTURE!r})")

    @pytest.mark.asyncio
    async def test_imports_two_plates_from_xlsx(self, fixture_bytes: bytes) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=fixture_bytes,
            filename="NadD.xlsx",
        )
        # Resolve only the one batch in the file. All others → unmatched & skipped.
        from cellar.infrastructure.parsers.tabular_file import parse_tabular as _pt

        table = _pt(fixture_bytes, "NadD.xlsx")
        suggested = infer_mapping(table)
        # Use suggested headers for column mapping
        mapping = ColumnMapping(
            well=suggested.first("well") or "Well",
            plate_name=suggested.first("plate_name"),
            concentration=suggested.first("concentration"),
            batch_ref=suggested.first("batch_ref"),
            readout_columns=(
                ReadoutColumn(
                    header=suggested.first("readout") or "Raw Data",
                    readout_definition_id=rd_id,
                ),
            ),
        )
        # Map every distinct batch ref in the file to the same fake batch.
        # We only need the batches resolver, so we hand-build it from the table.
        batch_refs = {
            (r.get(mapping.batch_ref) or "").strip()
            for r in table.iter_rows()
            if mapping.batch_ref and r.get(mapping.batch_ref)
        }
        batches = {ref: batch for ref in batch_refs if ref}

        uc, uow, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref=batches, store=store
        )

        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=mapping,
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.plates_created == 2
        # NadD has two plates of 384 wells but not every well has data — assert lower bound
        assert out.wells_created > 600
        # Protocol has no Control Layout configured, so blank wells fall through
        # to SAMPLE and are counted as unclassified.
        assert out.controls_unclassified > 0
        assert out.controls_from_template == 0
        assert uow.committed


# ---------------------------------------------------------------------------
# Conflict-aware re-import: skip-and-report
# ---------------------------------------------------------------------------


class TestConflictAwareReimport:
    """Re-imports must never silently overwrite existing data.

    Conflict unit is per-cell: ``(plate, well, readout_def)`` for readouts
    and ``(plate, well)`` for well metadata. Skipped cells/wells are
    reported on the result.
    """

    @pytest.mark.asyncio
    async def test_existing_readout_cell_skipped_with_conflict(self) -> None:
        """A re-imported readout cell that already has a value is left alone."""
        from cellar.domain.screening_assay.readout_data import ReadoutData
        from cellar.domain.screening_assay.run import Plate, Well
        from cellar.domain.shared.enums import Qualifier
        from cellar.domain.shared.value_objects import QualifiedValue

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        # Pre-populate one well with one readout already on the run.
        existing_plate = Plate(
            run_id=run.id,
            plate_number=1,
            format=PlateFormat.F384,
            plate_map={"name": "P1"},
        )
        existing_well = Well(
            plate_id=existing_plate.id,
            row="A",
            column=1,
            well_type=WellType.SAMPLE,
            batch_id=batch.id,
            dose=100.0,
        )
        run.plates.append(existing_plate)
        run.wells.append(existing_well)
        existing_readout = ReadoutData(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            well_id=existing_well.id,
            molecule_id=batch.molecule_id,
            batch_id=batch.id,
            readout_definition_id=rd_id,
            value=QualifiedValue(value=0.123, qualifier=Qualifier.EQUAL),
        )

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"P1,A1,100,LG-1,0.999\n"  # would overwrite if not skipped
            b"P1,A2,100,LG-1,0.5\n"  # new well — should write
        )
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="re-import.csv",
        )

        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
            existing_readouts=[existing_readout],
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        # No new plate; one new well (A2); one new readout (A2's Raw Data);
        # one readout conflict reported (A1's Raw Data).
        assert out.plates_created == 0
        assert out.wells_created == 1
        assert out.values_inserted == 1
        assert len(saved) == 1
        assert len(out.readout_conflicts) == 1
        c = out.readout_conflicts[0]
        assert c.plate_name == "P1"
        assert c.well_position == "A1"
        assert c.readout_definition_id == rd_id
        # Existing readout was NOT overwritten.
        assert existing_readout.value.value == 0.123

    @pytest.mark.asyncio
    async def test_a_new_readout_on_a_flagged_well_is_flagged_too(self) -> None:
        from cellar.domain.screening_assay.readout_data import ReadoutData
        from cellar.domain.screening_assay.run import Plate, Well
        from cellar.domain.shared.value_objects import QualifiedValue

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data", "Second"])
        raw_id, second_id = (rd.id for rd in protocol.readout_definitions)
        batch = FakeBatch()
        plate = Plate(run_id=run.id, plate_number=1, format=PlateFormat.F384)
        plate.plate_map = {"name": "P1"}
        flagged = Well(
            plate_id=plate.id,
            row="A",
            column=1,
            well_type=WellType.SAMPLE,
            batch_id=batch.id,
            dose=100.0,
        )
        run.plates.append(plate)
        run.wells.append(flagged)
        existing = ReadoutData(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            well_id=flagged.id,
            molecule_id=batch.molecule_id,
            batch_id=batch.id,
            readout_definition_id=raw_id,
            value=QualifiedValue(value=0.9),
            is_outlier=True,
        )
        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = (
            b"Plate Name,Well,Concentration,Batch,Second\nP1,A1,100,LG-1,0.4\nP1,A2,100,LG-1,0.5\n"
        )
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="b.csv",
        )
        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
            existing_readouts=[existing],
        )

        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate Name",
                    concentration="Concentration",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Second", readout_definition_id=second_id),
                    ),
                ),
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        by_well = {r.well_id: r.is_outlier for r in saved}
        assert by_well.pop(flagged.id) is True
        assert list(by_well.values()) == [False]  # A2, a new well

    @pytest.mark.asyncio
    async def test_well_metadata_mismatch_skips_row(self) -> None:
        """A row whose well metadata disagrees with the existing well is skipped entirely."""
        from cellar.domain.screening_assay.run import Plate, Well

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        existing_plate = Plate(
            run_id=run.id,
            plate_number=1,
            format=PlateFormat.F384,
            plate_map={"name": "P1"},
        )
        # Existing dose is 10 µM
        existing_well = Well(
            plate_id=existing_plate.id,
            row="A",
            column=1,
            well_type=WellType.SAMPLE,
            batch_id=batch.id,
            dose=10.0,
        )
        run.plates.append(existing_plate)
        run.wells.append(existing_well)

        store = InMemoryPreviewStore(ttl_seconds=60)
        # File claims 1 µM for A1 — mismatch.
        csv = b"Plate Name,Well,Concentration,Batch,Raw Data\nP1,A1,1,LG-1,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )

        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        # Whole row skipped — no readout written, no well created.
        assert out.wells_created == 0
        assert out.values_inserted == 0
        assert len(saved) == 0
        assert len(out.well_conflicts) == 1
        wc = out.well_conflicts[0]
        assert wc.plate_name == "P1"
        assert wc.well_position == "A1"
        assert "dose" in wc.reason

    @pytest.mark.asyncio
    async def test_new_plate_appends_cleanly(self) -> None:
        """A file with a brand-new plate name on a run that already has one
        plate creates the new plate and leaves the existing untouched."""
        from cellar.domain.screening_assay.run import Plate, Well

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        existing_plate = Plate(
            run_id=run.id,
            plate_number=1,
            format=PlateFormat.F384,
            plate_map={"name": "P1"},
        )
        existing_well = Well(
            plate_id=existing_plate.id,
            row="A",
            column=1,
            batch_id=batch.id,
            dose=10.0,
        )
        run.plates.append(existing_plate)
        run.wells.append(existing_well)

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Plate Name,Well,Concentration,Batch,Raw Data\nP2,A1,10,LG-1,0.7\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )

        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        assert out.plates_created == 1
        assert out.wells_created == 1
        assert out.values_inserted == 1
        # Run aggregate now has both plates
        assert len(run.plates) == 2
        plate_names = {(p.plate_map or {}).get("name") for p in run.plates}
        assert plate_names == {"P1", "P2"}

    @pytest.mark.asyncio
    async def test_text_readout_writes_when_numeric_already_present(self) -> None:
        """Same well, same plate — different readout def. The new one writes."""
        from cellar.domain.screening_assay.readout_data import ReadoutData
        from cellar.domain.screening_assay.run import Plate, Well
        from cellar.domain.shared.enums import Qualifier
        from cellar.domain.shared.value_objects import QualifiedValue

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data", "Scientist"])
        # Make Scientist a TEXT readout def
        protocol.readout_definitions[1].data_type = ReadoutDataType.TEXT
        raw_rd_id = protocol.readout_definitions[0].id
        scientist_rd_id = protocol.readout_definitions[1].id
        batch = FakeBatch()

        existing_plate = Plate(
            run_id=run.id,
            plate_number=1,
            format=PlateFormat.F384,
            plate_map={"name": "P1"},
        )
        existing_well = Well(
            plate_id=existing_plate.id,
            row="A",
            column=1,
            well_type=WellType.SAMPLE,
            batch_id=batch.id,
            dose=10.0,
        )
        run.plates.append(existing_plate)
        run.wells.append(existing_well)
        existing_readout = ReadoutData(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            well_id=existing_well.id,
            molecule_id=batch.molecule_id,
            batch_id=batch.id,
            readout_definition_id=raw_rd_id,
            value=QualifiedValue(value=0.123, qualifier=Qualifier.EQUAL),
        )

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Plate Name,Well,Concentration,Batch,Raw Data,Scientist\nP1,A1,10,LG-1,0.5,Dan\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )
        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            save_bulk=saved,
            existing_readouts=[existing_readout],
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=raw_rd_id),
                    ReadoutColumn(header="Scientist", readout_definition_id=scientist_rd_id),
                ),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        # Raw Data conflict; Scientist writes.
        assert out.values_inserted == 1
        assert len(out.readout_conflicts) == 1
        assert out.readout_conflicts[0].readout_definition_id == raw_rd_id
        # The one saved row is the Scientist text readout.
        assert len(saved) == 1
        assert saved[0].readout_definition_id == scientist_rd_id
        assert saved[0].value_text == "Dan"

    @pytest.mark.asyncio
    async def test_attaches_raw_file_on_success(self) -> None:
        """The raw upload bytes land as a Run attachment after a successful import."""
        from returns.result import Success as _Success

        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        batch = FakeBatch()

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Well,Batch,Raw Data\nA1,LG-1,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="run-data.csv",
        )

        # Capture the upload command for inspection.
        seen_cmds: list = []

        class _FakeAttachment:
            id = uuid.uuid4()

        async def _fake_upload(upload_cmd, auth=None):
            seen_cmds.append(upload_cmd)
            return _Success(_FakeAttachment())

        upload_mock = AsyncMock(side_effect=_fake_upload)

        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": batch},
            store=store,
            upload_attachment=upload_mock,
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    batch_ref="Batch",
                    readout_columns=(
                        ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        assert len(seen_cmds) == 1
        upload_cmd = seen_cmds[0]
        assert upload_cmd.file_data == csv
        assert upload_cmd.file_name == "run-data.csv"
        assert upload_cmd.attachable_id == run.id
        assert result.unwrap().attachment_id is not None


# ---------------------------------------------------------------------------
# Bare lot numbers in the batch column, next to a compound ref
# ---------------------------------------------------------------------------


@dataclass
class _FakeBatchNumber:
    value: str


@dataclass
class _FakeInventoryBatch:
    id: uuid.UUID
    batch_number: _FakeBatchNumber
    salt_name: str | None = None
    purity: float | None = None
    created_at: object = None


class TestBareLotNumbers:
    """CPD-1's lot "001" is registered as "CPD-1-001"; CPD-2's lot "002" is not."""

    CSV = (
        b"Molecule Name,Batch Name,Plate,Well,Raw Data\nCPD-1,001,P1,A1,0.5\nCPD-2,002,P1,A2,0.4\n"
    )

    def _world(self):
        mol1, mol2 = FakeMolecule(name="CPD-1"), FakeMolecule(name="CPD-2")
        b1, b2 = FakeBatch(molecule_id=mol1.id), FakeBatch(molecule_id=mol2.id)
        inventory = {
            mol1.id: [_FakeInventoryBatch(b1.id, _FakeBatchNumber("CC-1-001"))],
            mol2.id: [_FakeInventoryBatch(b2.id, _FakeBatchNumber("CC-2-001"))],
        }

        async def _batches_of(_ws, molecule_id):
            return inventory[molecule_id]

        return {"CPD-1": mol1, "CPD-2": mol2}, {"CPD-1-001": b1}, _batches_of, (b1, b2)

    @pytest.mark.asyncio
    async def test_preview_resolves_lots_and_notes_the_fallback(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        molecules, batches, batches_of, _ = self._world()
        uc, _ = _build_preview_uc(
            run=run,
            batches_by_ref=batches,
            molecules_by_synonym=molecules,
            protocol=_make_protocol(auth.workspace_id, ["Raw Data"]),
        )
        uc._batch_repo.find_by_molecule = batches_of
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=self.CSV,
                filename="x.csv",
            ),
            auth=auth,
        )
        preview = result.unwrap()
        assert preview.unmatched_batch_refs == ()
        assert preview.unmatched_compound_refs == ()
        assert preview.errors == ()
        assert LOTS_UNMATCHED_NOTE in preview.warnings

    @pytest.mark.asyncio
    async def test_import_writes_the_lots_batch_or_the_compounds_batch(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        molecules, batches, batches_of, (b1, b2) = self._world()
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=self.CSV,
            filename="x.csv",
        )
        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref=batches,
            store=store,
            save_bulk=saved,
            molecules_by_synonym=molecules,
        )
        uc._batch_repo.find_by_molecule = batches_of
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate",
                    batch_ref="Batch Name",
                    compound_ref="Molecule Name",
                    readout_columns=(
                        ReadoutColumn(
                            header="Raw Data",
                            readout_definition_id=protocol.readout_definitions[0].id,
                        ),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        assert sorted((r.value.value, r.batch_id) for r in saved) == [
            (0.4, b2.id),
            (0.5, b1.id),
        ]


# ---------------------------------------------------------------------------
# RepreviewRunFile — re-resolve a cached preview with a refined mapping
# ---------------------------------------------------------------------------


def _build_repreview_uc(
    *,
    run: Run,
    store: InMemoryPreviewStore,
    batches_by_ref: dict[str, FakeBatch] | None = None,
    protocol: Protocol | None = None,
    plate_templates: dict[uuid.UUID, PlateTemplate] | None = None,
) -> RepreviewRunFile:
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)

    batch_repo = AsyncMock()

    async def _find(_ws, ref):
        return (batches_by_ref or {}).get(ref)

    batch_repo.find_by_batch_number = _find
    batch_repo.find_by_molecule = AsyncMock(return_value=[])

    molecule_repo = AsyncMock()
    molecule_repo.find_by_identifier = AsyncMock(return_value=None)

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run = AsyncMock(return_value=[])
    readout_data_repo.has_wellless_rows = AsyncMock(return_value=False)

    return RepreviewRunFile(
        uow=FakeUoW(),
        run_repo=run_repo,
        readout_data_repo=readout_data_repo,
        batch_repo=batch_repo,
        molecule_repo=molecule_repo,
        preview_store=store,
        protocol_repo=protocol_repo,
        plate_template_repo=_make_plate_template_repo(plate_templates),
    )


class TestRepreviewRunFile:
    @pytest.mark.asyncio
    async def test_repreview_re_resolves_with_user_mapping(self) -> None:
        """Auto-guess mapped column to Batch Ref → 1 unmatched. User
        switches column to Compound Ref via repreview → batch_ref column
        is now empty so no unmatched_batches reported."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        store = InMemoryPreviewStore(ttl_seconds=60)
        # Stash a preview directly so we don't need a Preview round-trip.
        csv = b"Plate Name,Well,LGCY Batch Name,Concentration,Raw\nP1,A1,MMV2215819,50,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )
        uc = _build_repreview_uc(run=run, store=store, batches_by_ref={})

        # User maps the column as Compound Ref instead of Batch Ref.
        # No molecule matches in this test (find_by_identifier returns
        # None) so the value lands in unmatched_compound_refs, NOT
        # unmatched_batches.
        mapping = ColumnMapping(
            well="Well",
            plate_name="Plate Name",
            concentration="Concentration",
            compound_ref="LGCY Batch Name",
            readout_columns=(),
        )
        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=mapping,
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        preview = result.unwrap()
        # Same preview_id reused — caller can keep referring to it.
        assert preview.preview_id == preview_id
        # Mapping change took effect: no batch_ref column was used.
        assert preview.unmatched_batch_refs == ()
        assert "MMV2215819" in preview.unmatched_compound_refs

    @pytest.mark.asyncio
    async def test_repreview_does_not_consume_preview(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Well,Raw\nA1,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )
        uc = _build_repreview_uc(run=run, store=store)
        mapping = ColumnMapping(well="Well", readout_columns=())

        await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=mapping,
            ),
            auth=auth,
        )
        # Still in the store — chemist can repreview again or import.
        assert preview_id in store._items

    @pytest.mark.asyncio
    async def test_repreview_unknown_preview_id_returns_not_found(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        store = InMemoryPreviewStore(ttl_seconds=60)
        uc = _build_repreview_uc(run=run, store=store)
        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=uuid.uuid4(),
                mapping=ColumnMapping(well="Well", readout_columns=()),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_repreview_onto_a_run_whose_holder_is_not_a_plate_is_refused(self) -> None:
        auth = FakeAuth()
        run = _with_cassette(_make_run(auth.workspace_id))
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=b"Well,Raw\nA1,0.5\n",
            filename="x.csv",
        )
        uc = _build_repreview_uc(run=run, store=store)

        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(well="Well", readout_columns=()),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert str(result.failure()) == NOT_A_PLATE


# ---------------------------------------------------------------------------
# Auto-create missing batches (Sub-change B)
# ---------------------------------------------------------------------------


class TestAutoCreateMissingBatches:
    """Tests for auto_create_unmatched_batches flag on PreviewRunFile and ImportRunFile."""

    def _make_ensure_batch_exists_mock(
        self,
        batch: FakeBatch,
        *,
        created: bool = True,
    ) -> AsyncMock:
        """Return an AsyncMock that simulates EnsureBatchExists returning Success."""
        from returns.result import Success as _Success

        from cellar.application.inventory.ensure_batch_exists import EnsureBatchExistsOutcome

        mock_uc = AsyncMock()

        async def _side_effect(cmd, auth=None):
            return _Success(EnsureBatchExistsOutcome(batch=batch, created=created))

        mock_uc.side_effect = _side_effect
        return mock_uc

    @pytest.mark.asyncio
    async def test_preview_auto_creates_batch_when_flag_set(self) -> None:
        """When auto_create_unmatched_batches=True, a placeholder batch is created
        for an unmatched batch_ref whose compound_ref resolves to a molecule."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        mol = FakeMolecule()

        # batch_ref is MISSING-BATCH-X; compound_ref is MOL-NAME-X which resolves.
        new_batch = FakeBatch(molecule_id=mol.id)
        ensure_uc = self._make_ensure_batch_exists_mock(new_batch, created=True)

        run_repo = AsyncMock()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)

        batch_repo = AsyncMock()
        batch_repo.find_by_batch_number = AsyncMock(return_value=None)
        batch_repo.find_by_external_identifier = AsyncMock(return_value=None)

        molecule_repo = AsyncMock()

        async def _find_mol(_ws, ident):
            return mol if ident == "MOL-NAME-X" else None

        molecule_repo.find_by_identifier = _find_mol

        batch_repo.find_by_molecule = AsyncMock(return_value=[])

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_run = AsyncMock(return_value=[])
        readout_data_repo.has_wellless_rows = AsyncMock(return_value=False)

        store = InMemoryPreviewStore(ttl_seconds=60)

        uc = PreviewRunFile(
            uow=FakeUoW(),
            run_repo=run_repo,
            readout_data_repo=readout_data_repo,
            batch_repo=batch_repo,
            molecule_repo=molecule_repo,
            preview_store=store,
            protocol_repo=protocol_repo,
            plate_template_repo=_make_plate_template_repo(),
            parser=TabularFileParser(),
            ensure_batch_exists=ensure_uc,
        )

        csv = b"Plate Name,Well,Compound,Batch,Raw Data\nP1,A1,MOL-NAME-X,MISSING-BATCH-X,0.5\n"
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="test.csv",
                auto_create_unmatched_batches=True,
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        preview = result.unwrap()

        # EnsureBatchExists was called for the missing batch ref.
        ensure_uc.assert_called_once()
        call_cmd = ensure_uc.call_args[0][0]
        assert call_cmd.molecule_id == mol.id
        assert call_cmd.external_batch_ref == "MISSING-BATCH-X"
        assert "test.csv" in call_cmd.source_label

        # After auto-create, the ref resolved → not in unmatched list.
        assert "MISSING-BATCH-X" not in preview.unmatched_batch_refs
        assert preview.matched_batch_count == 1
        assert preview.auto_created_batches == 1

    @pytest.mark.asyncio
    async def test_preview_no_auto_create_when_flag_false(self) -> None:
        """With auto_create_unmatched_batches=False (default), EnsureBatchExists
        is never called and the ref stays unmatched."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        mol = FakeMolecule()
        ensure_uc = AsyncMock()

        run_repo = AsyncMock()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        batch_repo = AsyncMock()
        batch_repo.find_by_batch_number = AsyncMock(return_value=None)
        batch_repo.find_by_external_identifier = AsyncMock(return_value=None)
        batch_repo.find_by_molecule = AsyncMock(return_value=[])

        molecule_repo = AsyncMock()

        async def _find_mol(_ws, ident):
            return mol if ident == "MOL-NAME-X" else None

        molecule_repo.find_by_identifier = _find_mol

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=None)
        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_run = AsyncMock(return_value=[])
        readout_data_repo.has_wellless_rows = AsyncMock(return_value=False)

        store = InMemoryPreviewStore(ttl_seconds=60)
        uc = PreviewRunFile(
            uow=FakeUoW(),
            run_repo=run_repo,
            readout_data_repo=readout_data_repo,
            batch_repo=batch_repo,
            molecule_repo=molecule_repo,
            preview_store=store,
            protocol_repo=protocol_repo,
            plate_template_repo=_make_plate_template_repo(),
            parser=TabularFileParser(),
            ensure_batch_exists=ensure_uc,
        )

        csv = b"Plate Name,Well,Compound,Batch,Raw Data\nP1,A1,MOL-NAME-X,MISSING-BATCH-X,0.5\n"
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="test.csv",
                auto_create_unmatched_batches=False,  # flag off
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        preview = result.unwrap()
        ensure_uc.assert_not_called()
        assert "MISSING-BATCH-X" in preview.unmatched_batch_refs
        assert preview.auto_created_batches == 0

    @pytest.mark.asyncio
    async def test_import_auto_creates_batch_updates_result(self) -> None:
        """When auto_create_unmatched_batches=True on ImportRunFileCommand,
        the auto-created batch is picked up by resolve_rows and the result
        reflects it (auto_created_batches=1, row resolved)."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        mol = FakeMolecule()
        new_batch = FakeBatch(molecule_id=mol.id)
        ensure_uc = self._make_ensure_batch_exists_mock(new_batch, created=True)

        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = b"Plate Name,Well,Compound,Batch,Raw Data\nP1,A1,MOL-NAME-X,MISSING-BATCH-X,0.5\n"
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="test.csv",
        )

        saved: list = []
        uow = FakeUoW()
        run_repo = AsyncMock()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        run_repo.save = AsyncMock()

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

        batch_repo = AsyncMock()
        batch_repo.find_by_batch_number = AsyncMock(return_value=None)
        batch_repo.find_by_external_identifier = AsyncMock(return_value=None)

        molecule_repo = AsyncMock()

        async def _find_mol(_ws, ident):
            return mol if ident == "MOL-NAME-X" else None

        molecule_repo.find_by_identifier = _find_mol
        batch_repo.find_by_molecule = AsyncMock(return_value=[])

        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_run = AsyncMock(return_value=[])
        readout_data_repo.has_wellless_rows = AsyncMock(return_value=False)

        async def _save_bulk(entities):
            saved.extend(entities)

        readout_data_repo.save_bulk = _save_bulk

        from returns.result import Success as _Success

        class _FakeAttachment:
            id = uuid.uuid4()

        upload_attachment = AsyncMock()

        async def _no_op(*_a, **_kw):
            return _Success(_FakeAttachment())

        upload_attachment.side_effect = _no_op

        uc = ImportRunFile(
            uow=uow,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
            readout_data_repo=readout_data_repo,
            batch_repo=batch_repo,
            molecule_repo=molecule_repo,
            preview_store=store,
            plate_template_repo=_make_plate_template_repo(),
            upload_attachment=upload_attachment,
            ensure_batch_exists=ensure_uc,
        )

        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                compound_ref="Compound",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
            auto_create_unmatched_batches=True,
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        ensure_uc.assert_called_once()
        call_cmd = ensure_uc.call_args[0][0]
        assert call_cmd.molecule_id == mol.id
        assert call_cmd.external_batch_ref == "MISSING-BATCH-X"
        assert call_cmd.importing_user_id == auth.user_id

        assert out.auto_created_batches == 1
        # The batch resolved → not in unmatched list.
        assert "MISSING-BATCH-X" not in out.unmatched_batch_refs

    @pytest.mark.asyncio
    async def test_auto_create_skipped_when_compound_unresolved(self) -> None:
        """If the compound_ref for an unmatched batch_ref is also unknown,
        EnsureBatchExists must NOT be called — no molecule to attach to."""
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        ensure_uc = AsyncMock()

        run_repo = AsyncMock()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        batch_repo = AsyncMock()
        batch_repo.find_by_batch_number = AsyncMock(return_value=None)
        batch_repo.find_by_external_identifier = AsyncMock(return_value=None)
        batch_repo.find_by_molecule = AsyncMock(return_value=[])

        molecule_repo = AsyncMock()
        # compound_ref does NOT resolve
        molecule_repo.find_by_identifier = AsyncMock(return_value=None)

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=None)
        readout_data_repo = AsyncMock()
        readout_data_repo.find_by_run = AsyncMock(return_value=[])
        readout_data_repo.has_wellless_rows = AsyncMock(return_value=False)

        store = InMemoryPreviewStore(ttl_seconds=60)
        uc = PreviewRunFile(
            uow=FakeUoW(),
            run_repo=run_repo,
            readout_data_repo=readout_data_repo,
            batch_repo=batch_repo,
            molecule_repo=molecule_repo,
            preview_store=store,
            protocol_repo=protocol_repo,
            plate_template_repo=_make_plate_template_repo(),
            parser=TabularFileParser(),
            ensure_batch_exists=ensure_uc,
        )

        csv = b"Plate Name,Well,Compound,Batch,Raw Data\nP1,A1,UNKNOWN-MOL,MISSING-BATCH-X,0.5\n"
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="test.csv",
                auto_create_unmatched_batches=True,
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        preview = result.unwrap()
        # compound unresolved → no auto-create
        ensure_uc.assert_not_called()
        assert "MISSING-BATCH-X" in preview.unmatched_batch_refs
        assert preview.auto_created_batches == 0


# ---------------------------------------------------------------------------
# Import auto-link to inventory plates (S15 spec §5.3)
# ---------------------------------------------------------------------------


class TestImportAutoLinksInventoryPlate:
    """Every *new* plate the import creates is resolved by its file name
    against inventory; a miss (or a hidden plate) leaves the link null."""

    @staticmethod
    def _inventory(workspace_id: uuid.UUID, org_id: uuid.UUID, label: str):
        from types import SimpleNamespace

        from cellar.application.inventory.plate_visibility import PlateVisibilityService
        from cellar.domain.inventory.enums import PlateType
        from cellar.domain.inventory.registered_plate import RegisteredPlate
        from cellar.domain.shared.value_objects import Barcode
        from tests.fakes.fake_registered_plate_repository import (
            FakeRegisteredPlateRepository,
        )

        plate = RegisteredPlate.register(
            workspace_id=workspace_id,
            owner_org_id=org_id,
            barcode=Barcode(value="000777"),
            plate_label=label,
            format=PlateFormat.F96,
            plate_type=PlateType.ASSAY,
            registered_by=uuid.uuid4(),
        )

        class _Dir:
            async def list_orgs(self):
                return [SimpleNamespace(id=org_id), SimpleNamespace(id=uuid.uuid4())]

        return plate, FakeRegisteredPlateRepository([plate]), PlateVisibilityService(_Dir())

    async def _import(self, auth, plate_repo, visibility) -> Run:
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(auth.workspace_id, ["Raw Data"])
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"SAC3-014-3070,A1,100,LG-1,0.5\n"
            b"UNKNOWN-PLATE,A1,100,LG-1,0.4\n"
        )
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=csv,
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": FakeBatch()},
            store=store,
            plate_repo=plate_repo,
            plate_visibility=visibility,
        )
        cmd = ImportRunFileCommand(
            workspace_id=auth.workspace_id,
            run_id=run.id,
            preview_id=preview_id,
            mapping=ColumnMapping(
                well="Well",
                plate_name="Plate Name",
                concentration="Concentration",
                batch_ref="Batch",
                readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        assert result.unwrap().plates_created == 2
        return run

    async def test_matching_label_links_and_miss_stays_null(self) -> None:
        org_id = uuid.uuid4()
        auth = FakeAuth()
        auth.org_id = org_id
        rp, plate_repo, visibility = self._inventory(auth.workspace_id, org_id, "SAC3-014-3070")

        run = await self._import(auth, plate_repo, visibility)

        by_name = {p.plate_map["name"]: p for p in run.plates}
        assert by_name["SAC3-014-3070"].registered_plate_id == rp.id
        assert by_name["UNKNOWN-PLATE"].registered_plate_id is None

    async def test_hidden_foreign_org_plate_is_not_linked(self) -> None:
        auth = FakeAuth()
        auth.org_id = uuid.uuid4()
        _, plate_repo, visibility = self._inventory(
            auth.workspace_id, uuid.uuid4(), "SAC3-014-3070"
        )

        run = await self._import(auth, plate_repo, visibility)

        assert all(p.registered_plate_id is None for p in run.plates)

    async def test_without_inventory_wiring_nothing_links(self) -> None:
        auth = FakeAuth()
        run = await self._import(auth, None, None)
        assert all(p.registered_plate_id is None for p in run.plates)


# ---------------------------------------------------------------------------
# The file's well-role column ("Control State") decides control roles
# ---------------------------------------------------------------------------


# The protocol layout says A1 = positive, A2 = negative; the file says the opposite.
# A3 is a sample, A4 a blank the layout does not mention; H12 forces a 96-well plate.
_ROLE_CSV = (
    b"Plate Name,Well,Control State,Batch,Raw Data\n"
    b"P1,A1,negative control,,0.95\n"
    b"P1,A2,positive control,,0.07\n"
    b"P1,A3,,LG-1,0.5\n"
    b"P1,A4,blank,,0.01\n"
    b"P1,H12,,LG-1,0.4\n"
)


def _layout_protocol(auth: FakeAuth) -> tuple[Protocol, PlateTemplate]:
    tmpl = _make_plate_template(
        auth.workspace_id,
        fmt=PlateFormat.F96,
        template_map={"A1": "positive_control", "A2": "negative_control"},
    )
    protocol = _make_protocol(
        auth.workspace_id,
        ["Raw Data"],
        normalization=ReadoutNormalization.PERCENT_INHIBITION,
        control_layouts={PlateFormat.F96.value: tmpl.id},
    )
    return protocol, tmpl


def _role_mapping(rd_id: uuid.UUID, *, well_role: str | None = "Control State") -> ColumnMapping:
    return ColumnMapping(
        well="Well",
        plate_name="Plate Name",
        batch_ref="Batch",
        well_role=well_role,
        readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
    )


class TestWellRoleColumn:
    @pytest.mark.asyncio
    async def test_preview_counts_roles_from_the_file_and_says_where_it_differs(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        uc, _ = _build_preview_uc(
            run=run,
            batches_by_ref={"LG-1": FakeBatch()},
            protocol=protocol,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=_ROLE_CSV,
                filename="x.csv",
            ),
            auth=auth,
        )
        preview = result.unwrap()
        roles = {s.header: s.role for s in preview.suggestions}
        assert roles["Control State"] == "well_role"
        (plate,) = preview.plates
        assert (
            plate.sample_count,
            plate.positive_count,
            plate.negative_count,
            plate.reference_count,
            plate.blank_count,
        ) == (2, 1, 1, 0, 1)
        assert preview.validation_errors == ()
        assert plate.roles_from == 'the file\'s "Control State" column'
        assert preview.warnings == (
            'Control roles from the file\'s "Control State" column differ from the '
            'protocol default "Test Layout" on 3 wells.',
        )

    @pytest.mark.asyncio
    async def test_repreview_without_the_role_column_counts_the_layout(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV,
            filename="x.csv",
        )
        uc = _build_repreview_uc(
            run=run,
            protocol=protocol,
            store=store,
            batches_by_ref={"LG-1": FakeBatch()},
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(protocol.readout_definitions[0].id, well_role=None),
            ),
            auth=auth,
        )
        preview = result.unwrap()
        (plate,) = preview.plates
        # Layout: A1 positive, A2 negative; A4 (no compound, no layout entry) unclassified.
        assert (
            plate.sample_count,
            plate.positive_count,
            plate.negative_count,
            plate.reference_count,
            plate.blank_count,
        ) == (2, 1, 1, 0, 1)
        assert plate.roles_from == 'the protocol default "Test Layout"'
        assert preview.warnings == ()

    @pytest.mark.asyncio
    async def test_unknown_role_values_block_the_preview(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        csv = _ROLE_CSV.replace(b"P1,A4,blank", b"P1,A4,vehicle")
        uc, _ = _build_preview_uc(
            run=run,
            batches_by_ref={"LG-1": FakeBatch()},
            protocol=protocol,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=csv,
                filename="x.csv",
            ),
            auth=auth,
        )
        errors = result.unwrap().validation_errors
        assert len(errors) == 1
        assert '"Control State"' in errors[0] and '"vehicle"' in errors[0]

    @pytest.mark.asyncio
    async def test_import_writes_the_file_roles_and_keeps_controls_without_a_compound(
        self,
    ) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        rd_id = protocol.readout_definitions[0].id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV,
            filename="x.csv",
        )
        saved: list = []
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": FakeBatch()},
            store=store,
            save_bulk=saved,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(rd_id),
            ),
            auth=auth,
        )
        out = result.unwrap()
        types = {f"{w.row}{w.column}": w.well_type for w in run.wells}
        assert types == {
            "A1": WellType.NEGATIVE_CONTROL,
            "A2": WellType.POSITIVE_CONTROL,
            "A3": WellType.SAMPLE,
            "A4": WellType.BLANK,
            "H12": WellType.SAMPLE,
        }
        assert (out.controls_from_file, out.controls_from_template) == (3, 0)
        assert out.controls_unclassified == 0
        assert out.values_inserted == 5 and len(saved) == 5

    @pytest.mark.asyncio
    async def test_roles_from_the_file_need_no_protocol_layout(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
        )
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV,
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={"LG-1": FakeBatch()}, store=store
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(protocol.readout_definitions[0].id),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        assert result.unwrap().controls_from_file == 3

    @pytest.mark.asyncio
    async def test_import_refuses_unknown_role_values(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV.replace(b"P1,A4,blank", b"P1,A4,vehicle"),
            filename="x.csv",
        )
        uc, uow, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": FakeBatch()},
            store=store,
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(protocol.readout_definitions[0].id),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        assert '"vehicle"' in str(result.failure())
        assert not uow.committed and run.wells == []


# ---------------------------------------------------------------------------
# The run's own layout (runs.plate_template_id) comes before the protocol default
# ---------------------------------------------------------------------------


def _run_layout(auth: FakeAuth, fmt: PlateFormat = PlateFormat.F96) -> PlateTemplate:
    """The run's own layout: the protocol default turned around (A1 neg, A2 pos)."""
    tmpl = _make_plate_template(
        auth.workspace_id,
        fmt=fmt,
        template_map={"A1": "negative_control", "A2": "positive_control"},
    )
    tmpl.name = "Run Layout"
    return tmpl


class TestRunLayoutPrecedence:
    async def _repreview(self, run: Run, protocol: Protocol, templates, *, well_role=None):
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=run.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV,
            filename="x.csv",
        )
        uc = _build_repreview_uc(
            run=run,
            protocol=protocol,
            store=store,
            batches_by_ref={"LG-1": FakeBatch()},
            plate_templates={t.id: t for t in templates},
        )
        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=run.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(protocol.readout_definitions[0].id, well_role=well_role),
            ),
            auth=FakeAuth(workspace_id=run.workspace_id),
        )
        return result.unwrap()

    @pytest.mark.asyncio
    async def test_the_runs_layout_beats_the_protocol_default(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, default = _layout_protocol(auth)
        own = _run_layout(auth)
        run.plate_template_id = own.id
        preview = await self._repreview(run, protocol, [default, own])
        (plate,) = preview.plates
        assert plate.roles_from == 'this run\'s layout "Run Layout"'
        assert (plate.positive_count, plate.negative_count) == (1, 1)
        assert preview.warnings == (
            'Control roles from this run\'s layout "Run Layout" differ from the '
            'protocol default "Test Layout" on 2 wells.',
        )

    @pytest.mark.asyncio
    async def test_a_run_layout_of_another_plate_format_is_passed_over(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, default = _layout_protocol(auth)
        own = _run_layout(auth, fmt=PlateFormat.F384)
        run.plate_template_id = own.id
        preview = await self._repreview(run, protocol, [default, own])
        assert preview.plates[0].roles_from == 'the protocol default "Test Layout"'
        assert preview.warnings == ()

    @pytest.mark.asyncio
    async def test_the_file_column_is_compared_with_every_layout(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, default = _layout_protocol(auth)
        own = _run_layout(auth)
        run.plate_template_id = own.id
        preview = await self._repreview(run, protocol, [default, own], well_role="Control State")
        assert preview.plates[0].roles_from == 'the file\'s "Control State" column'
        # The file agrees with the run's layout on A1/A2; only its blank (A4) differs there.
        assert preview.warnings == (
            'Control roles from the file\'s "Control State" column differ from '
            'this run\'s layout "Run Layout" on 1 well.',
            'Control roles from the file\'s "Control State" column differ from the '
            'protocol default "Test Layout" on 3 wells.',
        )

    @pytest.mark.asyncio
    async def test_import_writes_the_runs_layout_and_needs_no_protocol_default(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol = _make_protocol(
            auth.workspace_id,
            ["Raw Data"],
            normalization=ReadoutNormalization.PERCENT_INHIBITION,
        )
        own = _run_layout(auth)
        run.plate_template_id = own.id
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_ROLE_CSV,
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            batches_by_ref={"LG-1": FakeBatch()},
            store=store,
            plate_templates={own.id: own},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=_role_mapping(protocol.readout_definitions[0].id, well_role=None),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        types = {f"{w.row}{w.column}": w.well_type for w in run.wells}
        assert (types["A1"], types["A2"]) == (
            WellType.NEGATIVE_CONTROL,
            WellType.POSITIVE_CONTROL,
        )
        assert result.unwrap().controls_from_template == 2


# ---------------------------------------------------------------------------
# Swap guard: controls whose raw signal reads the wrong way round
# ---------------------------------------------------------------------------


def _controls_table(
    pos: list[float], neg: list[float], *, words: tuple[str, str] = ("positive", "negative")
) -> tuple[NormalizedTable, uuid.UUID]:
    rd_id = uuid.uuid4()
    lines = ["Plate Name,Well,Control State,Raw Data"]
    lines += [f"P1,A{i + 1},{words[0]} control,{v}" for i, v in enumerate(pos)]
    lines += [f"P1,B{i + 1},{words[1]} control,{v}" for i, v in enumerate(neg)]
    lines += ["P1,C1,,0.5"]
    table = parse_tabular("\n".join(lines).encode(), "x.csv")
    mapping = ColumnMapping(
        well="Well",
        plate_name="Plate Name",
        well_role="Control State",
        readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
    )
    return normalize(table, mapping).unwrap(), rd_id


INHIBITION, ACTIVATION = False, True


class TestSwappedControls:
    """The full-effect control against the no-effect one: under HIGH the negative control
    is the full effect of an inhibition and the positive control that of an activation;
    LOW mirrors both."""

    def test_full_effect_reading_high_in_an_inhibition_is_flagged(self) -> None:
        norm, rd_id = _controls_table(pos=[0.1, 0.12], neg=[0.9, 0.92])
        assert _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.HIGH) == (
            "Plate P1: the full-effect controls (negative controls, mean 0.91) read higher "
            "than the no-effect controls (positive controls, mean 0.11); this protocol "
            "expects the full effect to lower the signal.",
        )

    def test_low_protocol_inhibition(self) -> None:
        norm, rd_id = _controls_table(pos=[0.1, 0.12], neg=[0.9, 0.92])
        assert _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.LOW) == ()
        norm, rd_id = _controls_table(pos=[0.9, 0.92], neg=[0.1, 0.12])
        (note,) = _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.LOW)
        assert note.startswith("Plate P1: the full-effect controls (positive controls, mean 0.91)")

    def test_activation_expects_the_full_effect_to_raise_the_signal(self) -> None:
        norm, rd_id = _controls_table(pos=[0.9, 0.92], neg=[0.1, 0.12])
        assert _swapped_controls(norm, {}, {rd_id: ACTIVATION}, PosControlSignal.HIGH) == ()
        assert _swapped_controls(norm, {}, {rd_id: ACTIVATION}, PosControlSignal.LOW) == (
            "Plate P1: the full-effect controls (negative controls, mean 0.11) read lower "
            "than the no-effect controls (positive controls, mean 0.91); this protocol "
            "expects the full effect to raise the signal.",
        )

    def test_platform_words_read_by_effect_pass_under_a_high_protocol(self) -> None:
        # The platform's hit control reads low, its negative control high: right for an
        # inhibition, once the words are read by effect.
        rd_id = uuid.uuid4()
        table = parse_tabular(
            b"Plate Name,Well,Control State,Raw Data\n"
            b"P1,A1,positive control (hit),0.07\nP1,A2,positive control (hit),0.08\n"
            b"P1,B1,negative control,0.95\nP1,B2,negative control,0.93\n",
            "x.csv",
        )
        mapping = ColumnMapping(
            well="Well",
            plate_name="Plate Name",
            well_role="Control State",
            readout_columns=(ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),),
        )
        norm = normalize(table, mapping, full_effect=WellType.NEGATIVE_CONTROL).unwrap()
        assert _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.HIGH) == ()

    def test_no_clear_separation_says_nothing(self) -> None:
        norm, rd_id = _controls_table(pos=[0.2, 0.8], neg=[0.3, 0.9])
        assert _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.HIGH) == ()

    def test_one_well_per_group_says_nothing(self) -> None:
        norm, rd_id = _controls_table(pos=[0.1], neg=[0.9])
        assert _swapped_controls(norm, {}, {rd_id: INHIBITION}, PosControlSignal.HIGH) == ()

    def test_readouts_not_normalized_against_controls_are_not_checked(self) -> None:
        norm, _ = _controls_table(pos=[0.1, 0.12], neg=[0.9, 0.92])
        assert _swapped_controls(norm, {}, {}, PosControlSignal.HIGH) == ()

    @pytest.mark.asyncio
    async def test_the_preview_flags_a_layout_that_swaps_the_controls(self) -> None:
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, default = _layout_protocol(auth)  # A1 pos, A2 neg; signal HIGH
        default.template_map = {
            "A1": "positive_control",
            "A2": "positive_control",
            "B1": "negative_control",
            "B2": "negative_control",
        }
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=(
                b"Plate Name,Well,Raw Data\n"
                b"P1,A1,0.1\nP1,A2,0.12\nP1,B1,0.9\nP1,B2,0.92\nP1,H12,0.5\n"
            ),
            filename="x.csv",
        )
        uc = _build_repreview_uc(
            run=run, protocol=protocol, store=store, plate_templates={default.id: default}
        )
        result = await uc(
            RepreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate Name",
                    readout_columns=(
                        ReadoutColumn(
                            header="Raw Data",
                            readout_definition_id=protocol.readout_definitions[0].id,
                        ),
                    ),
                ),
            ),
            auth=auth,
        )
        swapped = result.unwrap().swapped_controls
        assert len(swapped) == 1 and swapped[0].startswith("Plate P1: the full-effect controls")


# The external platform's export: its "positive control (hit)" is the full-effect control.
_PLATFORM_CSV = (
    b"Plate Name,Well,Control State,Raw Data\n"
    b"P1,A1,negative control,0.95\n"
    b"P1,A2,positive control (hit),0.07\n"
    b"P1,H12,,0.5\n"
)


class TestPlatformRoleWords:
    async def _preview(self, signal: PosControlSignal):
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)  # layout: A1 positive, A2 negative
        protocol.pos_control_signal = signal
        uc, _ = _build_preview_uc(run=run, protocol=protocol, plate_templates={tmpl.id: tmpl})
        result = await uc(
            PreviewRunFileQuery(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                file_content=_PLATFORM_CSV,
                filename="x.csv",
            ),
            auth=auth,
        )
        return result.unwrap()

    @pytest.mark.asyncio
    async def test_a_high_protocol_reads_the_hit_control_as_its_negative_control(self) -> None:
        preview = await self._preview(PosControlSignal.HIGH)
        # Read by effect the file agrees with the layout: A1 positive, A2 negative.
        assert preview.warnings == (
            'Control roles read by effect: "negative control" as positive control, '
            '"positive control (hit)" as negative control — under this protocol the '
            "negative control is the full-effect (hit) end.",
        )

    @pytest.mark.asyncio
    async def test_a_high_protocol_imports_the_hit_control_as_its_negative_control(self) -> None:
        # The import writes what the preview said: read by effect, not by the literal word.
        auth = FakeAuth()
        run = _make_run(auth.workspace_id)
        protocol, tmpl = _layout_protocol(auth)
        protocol.pos_control_signal = PosControlSignal.HIGH
        store = InMemoryPreviewStore(ttl_seconds=60)
        preview_id = _seed_preview(
            store,
            workspace_id=auth.workspace_id,
            run_id=run.id,
            file_content=_PLATFORM_CSV,
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run,
            protocol=protocol,
            store=store,
            batches_by_ref={},
            plate_templates={tmpl.id: tmpl},
        )
        result = await uc(
            ImportRunFileCommand(
                workspace_id=auth.workspace_id,
                run_id=run.id,
                preview_id=preview_id,
                mapping=ColumnMapping(
                    well="Well",
                    plate_name="Plate Name",
                    well_role="Control State",
                    readout_columns=(
                        ReadoutColumn(
                            header="Raw Data",
                            readout_definition_id=protocol.readout_definitions[0].id,
                        ),
                    ),
                ),
            ),
            auth=auth,
        )
        assert isinstance(result, Success), result
        types = {f"{w.row}{w.column}": w.well_type for w in run.wells}
        assert (types["A1"], types["A2"]) == (
            WellType.POSITIVE_CONTROL,
            WellType.NEGATIVE_CONTROL,
        )

    @pytest.mark.asyncio
    async def test_a_low_protocol_reads_the_hit_control_as_its_positive_control(self) -> None:
        preview = await self._preview(PosControlSignal.LOW)
        assert preview.warnings == (
            'Control roles from the file\'s "Control State" column differ from the '
            'protocol default "Test Layout" on 2 wells.',
            'Control roles read by effect: "negative control" as negative control, '
            '"positive control (hit)" as positive control — under this protocol the '
            "positive control is the full-effect (hit) end.",
        )
