"""Integration tests for workspace configuration persistence."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from cellar.domain.workspace_config.enums import OrganizationType
from cellar.domain.workspace_config.organization import Organization
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.controlled_vocabulary_repository import (
    SQLAlchemyControlledVocabularyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class TestOrganizationRepository:
    async def test_save_and_find_by_id(self, uow: AsyncUnitOfWork) -> None:
        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            org = Organization.create(
                workspace_id=uuid.uuid4(),
                name="Merck",
                org_type=OrganizationType.PHARMA_PARTNER,
            )
            await repo.save(org)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            loaded = await repo.find_by_id(org.id)
            assert loaded is not None
            assert loaded.name == "Merck"
            assert loaded.org_type == OrganizationType.PHARMA_PARTNER
            assert loaded.is_active is True
            assert loaded.version == 1

    async def test_update_with_version_increment(self, uow: AsyncUnitOfWork) -> None:
        org_id = uuid.uuid4()
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            org = Organization(
                id=org_id, workspace_id=ws_id, name="Old", org_type=OrganizationType.CRO
            )
            await repo.save(org)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            org = await repo.find_by_id(org_id)
            assert org is not None
            org.update(name="New Name")
            await repo.save(org)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            org = await repo.find_by_id(org_id)
            assert org is not None
            assert org.name == "New Name"
            assert org.version == 2

    async def test_find_by_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            await repo.save(
                Organization.create(
                    workspace_id=ws_id, name="Active Inc", org_type=OrganizationType.INTERNAL
                )
            )
            inactive = Organization.create(
                workspace_id=ws_id, name="Defunct Corp", org_type=OrganizationType.VENDOR
            )
            inactive.deactivate()
            await repo.save(inactive)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            active_only = await repo.find_by_workspace(ws_id)
            assert len(active_only) == 1
            assert active_only[0].name == "Active Inc"

            all_orgs = await repo.find_by_workspace(ws_id, include_inactive=True)
            assert len(all_orgs) == 2

    async def test_find_by_name(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            await repo.save(
                Organization.create(
                    workspace_id=ws_id, name="Eurofins Munich", org_type=OrganizationType.CRO
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemyOrganizationRepository(uow)
            found = await repo.find_by_name(ws_id, "Eurofins Munich")
            assert found is not None
            assert found.org_type == OrganizationType.CRO

            not_found = await repo.find_by_name(ws_id, "Nonexistent")
            assert not_found is None


# ---------------------------------------------------------------------------
# WorkspaceSettings
# ---------------------------------------------------------------------------


class TestWorkspaceSettingsRepository:
    async def test_save_and_find(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyWorkspaceSettingsRepository(uow)
            settings = WorkspaceSettings.create_default(workspace_id=ws_id)
            await repo.save(settings)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyWorkspaceSettingsRepository(uow)
            loaded = await repo.find_by_id(ws_id)
            assert loaded is not None
            assert loaded.workspace_id == ws_id
            assert loaded.registration_rules == {}
            assert loaded.version == 1

    async def test_update(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyWorkspaceSettingsRepository(uow)
            settings = WorkspaceSettings.create_default(workspace_id=ws_id)
            await repo.save(settings)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyWorkspaceSettingsRepository(uow)
            settings = await repo.find_by_id(ws_id)
            assert settings is not None
            settings.update(
                registration_rules={"numbering": "CV-{seq}"},
                signature_required_for=["registration"],
            )
            await repo.save(settings)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyWorkspaceSettingsRepository(uow)
            settings = await repo.find_by_id(ws_id)
            assert settings is not None
            assert settings.registration_rules == {"numbering": "CV-{seq}"}
            assert settings.signature_required_for == ["registration"]
            assert settings.version == 2


# ---------------------------------------------------------------------------
# ControlledVocabulary
# ---------------------------------------------------------------------------


class TestControlledVocabularyRepository:
    async def test_save_and_find_by_id(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocab = ControlledVocabulary.create(
                workspace_id=ws_id,
                name="Species",
                terms=["Human", "Mouse", "Rat"],
                created_by=user_id,
            )
            await repo.save(vocab)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            loaded = await repo.find_by_id(vocab.id)
            assert loaded is not None
            assert loaded.name == "Species"
            assert loaded.terms == ["Human", "Mouse", "Rat"]
            assert loaded.created_by == user_id

    async def test_find_by_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            await repo.save(
                ControlledVocabulary.create(
                    workspace_id=ws_id, name="Assay Type", created_by=user_id
                )
            )
            await repo.save(
                ControlledVocabulary.create(
                    workspace_id=ws_id, name="Species", created_by=user_id
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocabs = await repo.find_by_workspace(ws_id)
            assert len(vocabs) == 2
            assert vocabs[0].name == "Assay Type"  # ordered by name
            assert vocabs[1].name == "Species"

    async def test_find_by_name(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            await repo.save(
                ControlledVocabulary.create(
                    workspace_id=ws_id, name="Route", created_by=user_id
                )
            )
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            found = await repo.find_by_name(ws_id, "Route")
            assert found is not None
            assert found.name == "Route"

    async def test_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocab = ControlledVocabulary.create(
                workspace_id=ws_id, name="Deletable", created_by=user_id
            )
            await repo.save(vocab)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            await repo.delete(ws_id, vocab.id)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            assert await repo.find_by_id(vocab.id) is None

    async def test_update_terms(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocab = ControlledVocabulary.create(
                workspace_id=ws_id, name="Species", terms=["Human"], created_by=user_id
            )
            await repo.save(vocab)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocab = await repo.find_by_id(vocab.id)
            assert vocab is not None
            vocab.add_term("Mouse")
            await repo.save(vocab)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyControlledVocabularyRepository(uow)
            vocab = await repo.find_by_id(vocab.id)
            assert vocab is not None
            assert vocab.terms == ["Human", "Mouse"]
            assert vocab.version == 2
