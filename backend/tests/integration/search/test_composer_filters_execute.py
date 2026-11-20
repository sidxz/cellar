"""Text, property, custom-field, keyword, collection and group criteria pick molecules."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (  # noqa: E501
    compose_criteria,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
)

from .conftest import _make_molecule_model

ATORVASTATIN = "CC(C)c1n(CCC(O)CC(O)CC(=O)O)c(-c2ccc(F)cc2)c(-c2ccccc2)c1C(=O)Nc1ccccc1"
# name: (smiles, molecular weight, logP, custom fields)
MOLECULES = {
    "Aspirin": (
        "CC(=O)Oc1ccccc1C(=O)O",
        180.16,
        1.31,
        {"project_code": "ABC-12", "solubility": "0.8"},
    ),
    "Ibuprofen": (
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        206.28,
        3.07,
        {"project_code": "XYZ-1", "solubility": "n/a"},
    ),
    "Atorvastatin": (ATORVASTATIN, 558.64, 4.46, {"source": "CRO-1", "score": 5}),
}


@pytest.fixture
async def molecules(
    db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
) -> dict[str, MoleculeModel]:
    seeded = {}
    for number, (name, (smiles, mw, logp, custom)) in enumerate(MOLECULES.items(), start=1):
        model = _make_molecule_model(workspace_id, org_id, smiles=smiles, name=name)
        model.registration_number = f"CV-{number:05d}"
        model.molecular_weight, model.logp, model.custom_fields = mw, logp, custom
        db_session.add(model)
        seeded[name] = model
    await db_session.flush()
    return seeded


async def _names(
    session: AsyncSession, workspace_id: uuid.UUID, criteria: list[dict], logic: str = "and"
) -> set[str]:
    clause = compose_criteria({"criteria": criteria, "logic": logic}, workspace_id=workspace_id)
    names = await session.scalars(
        select(MoleculeModel.name).where(MoleculeModel.workspace_id == workspace_id, clause)
    )
    return set(names)


def _text(field: str, operator: str, value: str, **extra: object) -> dict:
    return {"type": "text", "field": field, "operator": operator, "value": value, **extra}


def _prop(field: str, operator: str, **bounds: object) -> dict:
    return {"type": "property", "field": field, "operator": operator, **bounds}


def _custom(field: str, mode: str, operator: str, **bounds: object) -> dict:
    return {"type": "custom_field", "field": field, "mode": mode, "operator": operator, **bounds}


def _group(logic: str, *criteria: dict) -> dict:
    return {"type": "group", "logic": logic, "criteria": list(criteria)}


@pytest.mark.parametrize(
    ("criteria", "logic", "expected"),
    [
        ([_text("name", "equals", "Aspirin")], "and", {"Aspirin"}),
        ([_prop("molecular_weight", "between", min=200, max=500)], "and", {"Ibuprofen"}),
        ([_prop("logp", "lte", value=3.0)], "and", {"Aspirin"}),
        (
            [_text("name", "contains", "in"), _prop("molecular_weight", "lte", value=500)],
            "and",
            {"Aspirin"},
        ),
        (
            [_text("name", "contains", "aspirin"), _text("name", "contains", "ibuprofen")],
            "or",
            {"Aspirin", "Ibuprofen"},
        ),
        (
            [_prop("molecular_weight", "gt", value=500, negate=True)],
            "and",
            {"Aspirin", "Ibuprofen"},
        ),
        (
            [
                _group(
                    "and",
                    _group(
                        "or",
                        _text("name", "equals", "Aspirin"),
                        _text("name", "equals", "Ibuprofen"),
                    ),
                    _group("or", _prop("logp", "gt", value=4), _prop("logp", "lt", value=2)),
                )
            ],
            "and",
            {"Aspirin"},
        ),
        ([_custom("project_code", "text", "contains", value="abc")], "and", {"Aspirin"}),
        ([_custom("source", "text", "equals", value="CRO-1")], "and", {"Atorvastatin"}),
        # Ibuprofen's "n/a" reads as no value instead of failing the cast.
        ([_custom("solubility", "numeric", "gt", value=0.5)], "and", {"Aspirin"}),
        ([_custom("score", "numeric", "between", min=1, max=10)], "and", {"Atorvastatin"}),
    ],
)
async def test_criteria_select_matching_molecules(
    db_session: AsyncSession,
    workspace_id: uuid.UUID,
    molecules: dict[str, MoleculeModel],
    criteria: list[dict],
    logic: str,
    expected: set[str],
) -> None:
    assert await _names(db_session, workspace_id, criteria, logic) == expected


async def test_keyword_list_matches_registration_numbers_and_ids(
    db_session: AsyncSession, workspace_id: uuid.UUID, molecules: dict[str, MoleculeModel]
) -> None:
    by_number = {"type": "keyword_list", "ref_type": "registration_number", "values": ["cv-00001"]}
    by_id = {"type": "keyword_list", "ref_type": "uuid", "values": [molecules["Ibuprofen"].id]}

    assert await _names(db_session, workspace_id, [by_number]) == {"Aspirin"}
    assert await _names(db_session, workspace_id, [by_id]) == {"Ibuprofen"}


async def test_collection_matches_its_members_only(
    db_session: AsyncSession, workspace_id: uuid.UUID, molecules: dict[str, MoleculeModel]
) -> None:
    collection = CollectionModel(
        id=uuid.uuid4(), workspace_id=workspace_id, name="Hits", created_by=uuid.uuid4(), version=1
    )
    db_session.add(collection)
    await db_session.flush()
    db_session.add(
        CollectionMoleculeModel(collection_id=collection.id, molecule_id=molecules["Aspirin"].id)
    )
    await db_session.flush()
    criterion = {"type": "collection", "collection_id": str(collection.id)}

    assert await _names(db_session, workspace_id, [criterion]) == {"Aspirin"}
    assert await _names(db_session, workspace_id, [{**criterion, "negate": True}]) == {
        "Ibuprofen",
        "Atorvastatin",
    }
