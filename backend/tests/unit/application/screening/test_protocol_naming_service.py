import uuid
from dataclasses import dataclass

from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.domain.screening_assay.enums import NameFlag
from cellar.domain.screening_assay.repository import NameSibling
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings

WS = uuid.uuid4()
MTB = OntologyTerm(
    term_id="http://purl.bioontology.org/ontology/NCBITAXON/1773",
    label="Mycobacterium tuberculosis",
    ontology_source="NCBITAXON",
)


@dataclass
class _Target:
    id: uuid.UUID
    name: str
    organism: str | None


class _Protocols:
    def __init__(self, siblings=()):
        self.siblings = list(siblings)
        self.flagged = {}

    async def find_name_siblings(self, workspace_id, *, base, exclude_code):
        return [
            s
            for s in self.siblings
            if s.name.lower().startswith(base.lower()) and s.code != exclude_code
        ]

    async def lock_naming(self, workspace_id):
        return None

    async def find_by_id_in_workspace(self, workspace_id, protocol_id):
        return None  # sibling flagging is covered by the integration test

    async def find_direct_target_ids(self, workspace_id, protocol_id):
        return []


class _Targets:
    def __init__(self, targets=()):
        self.targets = {t.id: t for t in targets}

    async def find_by_ids(self, workspace_id, ids):
        return [self.targets[i] for i in ids if i in self.targets]


class _Categories:
    async def find_by_label(self, workspace_id, label):
        if label and label.lower() in ("growth inhibition", "enzyme inhibition"):
            return ProtocolCategory.create(workspace_id=workspace_id, label=label.capitalize())
        return None


class _Labels:
    async def find_by_workspace(self, workspace_id):
        return []


class _Settings:
    async def find_by_workspace_id(self, workspace_id):
        s = WorkspaceSettings.create_default(workspace_id=workspace_id)
        s.set_home_organism({"term_id": MTB.term_id, "label": MTB.label})
        return s


class _Collections:
    async def find_by_workspace(self, workspace_id, **_):
        return []


def _service(siblings=(), targets=()):
    return ProtocolNameService(
        protocol_repo=_Protocols(siblings),
        target_repo=_Targets(targets),
        category_repo=_Categories(),
        label_repo=_Labels(),
        settings_repo=_Settings(),
        collection_repo=_Collections(),
    )


async def test_derives_from_category_and_organism():
    d = await _service().derive(
        WS,
        category="Growth inhibition",
        target_ids=[],
        annotations={"organism": [MTB]},
        discriminator="resazurin",
    )
    assert d.rendered.name == "M. tuberculosis growth inhibition [resazurin]" and d.clash is None


async def test_unknown_category_is_missing_not_a_crash():
    d = await _service().derive(
        WS, category="Enzyme Assay", target_ids=[], annotations={}, discriminator=None
    )
    assert d.rendered.missing == ("category",)
    assert (
        _service().check(d, person=True, allow_incomplete=False).failure().__class__
        is ValidationError
    )
    assert _service().check(d, person=True, allow_incomplete=True).unwrap() == NameFlag.NEEDS_FACTS


async def test_same_base_without_discriminator_conflicts_for_people_and_flags_for_the_system():
    sibling = NameSibling(
        protocol_id=uuid.uuid4(),
        code="PRT-00002",
        name="M. tuberculosis growth inhibition [OD600]",
        discriminator="OD600",
    )
    d = await _service([sibling]).derive(
        WS,
        category="Growth inhibition",
        target_ids=[],
        annotations={"organism": [MTB]},
        discriminator=None,
    )
    assert d.needs_discriminator
    assert isinstance(
        _service().check(d, person=True, allow_incomplete=False).failure(), ConflictError
    )
    assert (
        _service().check(d, person=False, allow_incomplete=False).unwrap()
        == NameFlag.NEEDS_DISCRIMINATOR
    )


async def test_exact_clash_names_the_other_code():
    sibling = NameSibling(
        protocol_id=uuid.uuid4(),
        code="PRT-00002",
        name="M. tuberculosis growth inhibition [OD600]",
        discriminator="OD600",
    )
    d = await _service([sibling]).derive(
        WS,
        category="Growth inhibition",
        target_ids=[],
        annotations={"organism": [MTB]},
        discriminator="od600",
    )
    assert d.clash == sibling
    assert "PRT-00002" in str(_service().check(d, person=True, allow_incomplete=False).failure())


async def test_bare_sibling_is_reported_for_flagging():
    bare = NameSibling(
        protocol_id=uuid.uuid4(),
        code="PRT-00003",
        name="M. tuberculosis growth inhibition",
        discriminator=None,
    )
    d = await _service([bare]).derive(
        WS,
        category="Growth inhibition",
        target_ids=[],
        annotations={"organism": [MTB]},
        discriminator="hypoxia",
    )
    assert d.bare_siblings == (bare,) and not d.needs_discriminator and d.clash is None


async def test_targets_come_from_the_registry_in_name_order():
    a, b = _Target(uuid.uuid4(), "PanD", MTB.label), _Target(uuid.uuid4(), "PanC", MTB.label)
    d = await _service(targets=[a, b]).derive(
        WS,
        category="Enzyme inhibition",
        target_ids=[a.id, b.id],
        annotations={},
        discriminator=None,
    )
    assert d.rendered.name == "PanC/PanD inhibition"


async def test_an_incomplete_name_never_overwrites_an_existing_one():
    from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
    from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition

    pid = uuid.uuid4()
    legacy = Protocol.create(
        workspace_id=WS,
        name="Legacy hand-typed name",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        code="PRT-00009",
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)
        ],
    )
    result = await _service().apply(legacy, reason="Names generated", person=False, allow_incomplete=True)
    assert result.unwrap().rendered.missing == ("category",)
    assert legacy.name == "Legacy hand-typed name" and legacy.aliases == []
    assert legacy.name_flag == NameFlag.NEEDS_FACTS
