"""Unit tests for ImportRunFile + PreviewRunFile use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.import_run_file import (
    ImportRunFile,
    ImportRunFileCommand,
    InMemoryPreviewStore,
    PreviewRunFile,
    PreviewRunFileQuery,
)
from chem_vault.application.screening.long_format_normalizer import (
    ColumnMapping,
    ReadoutColumn,
    infer_mapping,
)
from chem_vault.domain.screening_assay.enums import (
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from chem_vault.domain.screening_assay.plate_template import PlateTemplate
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.enums import PlateFormat
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.infrastructure.parsers.tabular_file import TabularFileParser, parse_tabular


_NADD_FIXTURE = "/Users/sidx/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx"


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


def _make_protocol(
    workspace_id: uuid.UUID,
    readout_names: list[str],
    *,
    normalization: ReadoutNormalization = ReadoutNormalization.NONE,
    control_layouts: dict[str, uuid.UUID] | None = None,
) -> Protocol:
    norm_set = (
        frozenset({normalization})
        if normalization != ReadoutNormalization.NONE
        else frozenset()
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
    molecules_by_synonym: dict[str, "FakeMolecule"] | None = None,
    store: InMemoryPreviewStore | None = None,
    protocol: Protocol | None = None,
    plate_templates: dict[uuid.UUID, PlateTemplate] | None = None,
    existing_readouts: list | None = None,
) -> tuple[PreviewRunFile, InMemoryPreviewStore]:
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)

    batch_repo = AsyncMock()

    async def _find(_ws, ref):
        return (batches_by_ref or {}).get(ref)

    batch_repo.find_by_batch_number = _find

    molecule_repo = AsyncMock()

    async def _find_mol(_ws, ident):
        return (molecules_by_synonym or {}).get(ident)

    molecule_repo.find_by_identifier = _find_mol

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run = AsyncMock(return_value=existing_readouts or [])

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
    molecules_by_synonym: dict[str, "FakeMolecule"] | None = None,
    plate_templates: dict[uuid.UUID, PlateTemplate] | None = None,
    existing_readouts: list | None = None,
    upload_attachment=None,
) -> tuple[ImportRunFile, FakeUoW, AsyncMock]:
    uow = FakeUoW()

    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    run_repo.save = AsyncMock()

    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)

    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run = AsyncMock(return_value=existing_readouts or [])
    saved_list = save_bulk if save_bulk is not None else []

    async def _save_bulk(entities):
        saved_list.extend(entities)

    readout_data_repo.save_bulk = _save_bulk

    batch_repo = AsyncMock()

    async def _find(_ws, ref):
        return batches_by_ref.get(ref)

    batch_repo.find_by_batch_number = _find

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
        assert preview.total_rows == 3
        assert len(preview.plates) == 1
        plate = preview.plates[0]
        assert plate.plate_name == "P1"
        assert plate.sample_count == 2
        assert plate.blank_count == 1
        assert preview.matched_batches == 1
        assert preview.unmatched_batches == ()
        # Cached for follow-up import
        assert preview.preview_id in store._items  # noqa: SLF001

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
        assert preview.unmatched_batches == ("LG-MISSING",)
        assert preview.matched_batches == 0


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
    import time

    from chem_vault.application.screening.import_run_file import _StoredPreview

    table = parse_tabular(file_content, filename)
    preview_id = uuid.uuid4()
    store.save(
        preview_id,
        _StoredPreview(
            workspace_id=workspace_id,
            run_id=run_id,
            table=table,
            raw_bytes=file_content,
            filename=filename,
            content_type="text/csv",
            expires_at=time.monotonic() + 60,
        ),
    )
    return preview_id


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
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                ),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.plates_created == 1
        # Sample wells (A1, A2) + blank (A3) — all 3 wells created
        assert out.wells_created == 3
        # Readouts written for all wells with values, including the blank
        # (control wells need raw values for plate normalization).
        assert out.readouts_created == 3
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
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                ),
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
        uc, _, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={}, store=store
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
        uc, _, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={}, store=store
        )
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
                b"Well,Batch,Raw Data\n"
                b"A1,LG-MISSING,0.5\n"
                b"A2,,0.9\n"  # blank — no batch
            ),
            filename="x.csv",
        )
        uc, _, _ = _build_import_uc(
            run=run, protocol=protocol, batches_by_ref={}, store=store
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
        out = result.unwrap()
        assert out.unmatched_batches == ["LG-MISSING"]
        # A1 was skipped (unmatched), A2 is a blank — only one well created.
        assert out.wells_created == 1
        # The blank well still gets its readout written (non-sample readouts
        # have None molecule/batch and feed plate normalization).
        assert out.readouts_created == 1

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
            file_content=(
                b"Well,Batch,Raw Data\n"
                b"A1,,0.07\n"
                b"A2,,0.95\n"
                b"A3,LG-1,0.5\n"
                b"H12,LG-1,0.5\n"
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
                b"A1,100,,0.07\n"   # POS control with inhibitor concentration
                b"A2,,,0.95\n"      # NEG control, blank conc
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
                b"A2,,0.95\n"             # NEG, blank
                b"A3,LG-MISSING,0.5\n"   # SAMPLE w/ unresolved — skip
                b"H12,,0.5\n"             # corner — 96-well
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
            pytest.skip(f"NadD fixture missing at {_NADD_FIXTURE}")

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
        from chem_vault.infrastructure.parsers.tabular_file import parse_tabular as _pt

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
        from chem_vault.domain.screening_assay.readout_data import ReadoutData
        from chem_vault.domain.screening_assay.run import Plate, Well
        from chem_vault.domain.shared.value_objects import QualifiedValue
        from chem_vault.domain.shared.enums import Qualifier

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
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                ),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        # No new plate; one new well (A2); one new readout (A2's Raw Data);
        # one readout conflict reported (A1's Raw Data).
        assert out.plates_created == 0
        assert out.wells_created == 1
        assert out.readouts_created == 1
        assert len(saved) == 1
        assert len(out.conflicts_readout) == 1
        c = out.conflicts_readout[0]
        assert c.plate_name == "P1"
        assert c.well_position == "A1"
        assert c.readout_definition_id == rd_id
        # Existing readout was NOT overwritten.
        assert existing_readout.value.value == 0.123

    @pytest.mark.asyncio
    async def test_well_metadata_mismatch_skips_row(self) -> None:
        """A row whose well metadata disagrees with the existing well is skipped entirely."""
        from chem_vault.domain.screening_assay.run import Plate, Well

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
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"P1,A1,1,LG-1,0.5\n"
        )
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
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                ),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        # Whole row skipped — no readout written, no well created.
        assert out.wells_created == 0
        assert out.readouts_created == 0
        assert len(saved) == 0
        assert len(out.conflicts_well_metadata) == 1
        wc = out.conflicts_well_metadata[0]
        assert wc.plate_name == "P1"
        assert wc.well_position == "A1"
        assert "dose" in wc.reason

    @pytest.mark.asyncio
    async def test_new_plate_appends_cleanly(self) -> None:
        """A file with a brand-new plate name on a run that already has one
        plate creates the new plate and leaves the existing untouched."""
        from chem_vault.domain.screening_assay.run import Plate, Well

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
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data\n"
            b"P2,A1,10,LG-1,0.7\n"
        )
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
                readout_columns=(
                    ReadoutColumn(header="Raw Data", readout_definition_id=rd_id),
                ),
            ),
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        out = result.unwrap()

        assert out.plates_created == 1
        assert out.wells_created == 1
        assert out.readouts_created == 1
        # Run aggregate now has both plates
        assert len(run.plates) == 2
        plate_names = {(p.plate_map or {}).get("name") for p in run.plates}
        assert plate_names == {"P1", "P2"}

    @pytest.mark.asyncio
    async def test_text_readout_writes_when_numeric_already_present(self) -> None:
        """Same well, same plate — different readout def. The new one writes."""
        from chem_vault.domain.screening_assay.readout_data import ReadoutData
        from chem_vault.domain.screening_assay.run import Plate, Well
        from chem_vault.domain.shared.value_objects import QualifiedValue
        from chem_vault.domain.shared.enums import Qualifier

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
        csv = (
            b"Plate Name,Well,Concentration,Batch,Raw Data,Scientist\n"
            b"P1,A1,10,LG-1,0.5,Dan\n"
        )
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
        assert out.readouts_created == 1
        assert len(out.conflicts_readout) == 1
        assert out.conflicts_readout[0].readout_definition_id == raw_rd_id
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
