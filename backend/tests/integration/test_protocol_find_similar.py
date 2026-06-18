from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _make(ws: uuid.UUID, name: str, readouts: list[str]) -> Protocol:
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in readouts
        ],
    )


async def test_find_similar_flags_run_candidate_and_excludes_unrelated(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    rnap = _make(ws, "RNAP core IC50", ["IC50", "Hill slope", "R squared"])
    unrelated = _make(ws, "Cell viability MTT", ["% viability"])
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(rnap)
        await repo.save(unrelated)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        matches = await repo.find_similar(
            ws,
            name="RNAP core IC50 GSK4329-31 before plates",
            protocol_type="biochemical",
            target_ids=[],
            readout_names=["IC50", "Hill slope", "R squared"],
        )

    names = [m.name for m in matches]
    assert "RNAP core IC50" in names
    assert "Cell viability MTT" not in names
    top = matches[0]
    assert top.name == "RNAP core IC50"
    assert top.is_run_candidate is True
    assert "ic50" in top.shared_readout_kinds


async def test_find_similar_facet_overlap_boosts_score(uow: AsyncUnitOfWork) -> None:
    from cellar.domain.shared.ontology import OntologyTerm

    ws = uuid.uuid4()
    faceted = _make(ws, "RNAP core IC50", ["IC50", "Hill slope"])
    faceted.set_ontology_annotation(
        "organism",
        [OntologyTerm(term_id="NCBITaxon:1773", label="Mtb", ontology_source="NCBITAXON")],
    )
    plain = _make(ws, "RNAP core IC50 clone", ["IC50", "Hill slope"])
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(faceted)
        await repo.save(plain)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        matches = await repo.find_similar(
            ws,
            name="RNAP core IC50",
            protocol_type="biochemical",
            target_ids=[],
            readout_names=["IC50", "Hill slope"],
            facet_ids=["ncbitaxon:1773"],
        )
    by_name = {m.name: m.score for m in matches}
    assert by_name["RNAP core IC50"] > by_name["RNAP core IC50 clone"]
