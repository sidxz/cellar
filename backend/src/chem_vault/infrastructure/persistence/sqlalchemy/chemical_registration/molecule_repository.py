"""SQLAlchemy repository for Molecule aggregates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chem_vault.domain.chemical_registration.enums import (
    ComponentRole,
    IdentifierType,
    LifecycleStage,
    MoleculeType,
    RegistrationStatus,
    Stereochemistry,
    StructureStatus,
    SynthesisStatus,
)
from chem_vault.domain.chemical_registration.mixture_component import MixtureComponent
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    PredictedProperties,
    RegistrationNumber,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MixtureComponentModel,
    MoleculeIdentifierModel,
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    molecule_projects,
)


class SQLAlchemyMoleculeRepository(
    SQLAlchemyRepository[Molecule, MoleculeModel]
):
    model_class = MoleculeModel

    # ------------------------------------------------------------------
    # Mapping: SA model -> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: MoleculeModel) -> Molecule:
        # Build VOs (all-null or all-populated)
        structure: ChemicalStructure | None = None
        if model.smiles is not None:
            structure = ChemicalStructure(
                smiles=model.smiles,
                cxsmiles=model.cxsmiles,
                inchi=model.inchi,
                inchi_key=model.inchi_key,
                molfile=model.molfile,
            )

        descriptors: ComputedDescriptors | None = None
        if model.molecular_weight is not None:
            descriptors = ComputedDescriptors(
                molecular_formula=model.molecular_formula,
                molecular_weight=model.molecular_weight,
                exact_mass=model.exact_mass,
                logp=model.logp,
                tpsa=model.tpsa,
                hbd=model.hbd,
                hba=model.hba,
                rotatable_bonds=model.rotatable_bonds,
                aromatic_rings=model.aromatic_rings,
                ring_count=model.ring_count,
                heavy_atom_count=model.heavy_atom_count,
                ro5_violations=model.ro5_violations,
            )

        predicted: PredictedProperties | None = None
        if any(v is not None for v in (model.logd, model.pka, model.logs)):
            predicted = PredictedProperties(
                logd=model.logd,
                pka=model.pka,
                logs=model.logs,
                prediction_source=model.prediction_source,
                predicted_at=model.predicted_at,
            )

        identifiers = [
            MoleculeIdentifier(
                id=ident.id,
                molecule_id=ident.molecule_id,
                identifier=ident.identifier,
                identifier_type=IdentifierType(ident.identifier_type),
                source=ident.source,
                registered_by=ident.registered_by,
                created_at=ident.created_at,
            )
            for ident in model.identifiers
        ]

        mixture_components = [
            MixtureComponent(
                id=comp.id,
                mixture_molecule_id=comp.mixture_molecule_id,
                component_molecule_id=comp.component_molecule_id,
                stoichiometric_ratio=comp.stoichiometric_ratio,
                role=ComponentRole(comp.role),
            )
            for comp in model.mixture_components
        ]

        return Molecule(
            id=model.id,
            workspace_id=model.workspace_id,
            registration_number=RegistrationNumber(value=model.registration_number),
            name=model.name,
            molecule_type=MoleculeType(model.molecule_type),
            structure=structure,
            descriptors=descriptors,
            predicted_properties=predicted,
            molecular_formula=model.molecular_formula,
            structure_image_key=model.structure_image_key,
            sequence=model.sequence,
            stereochemistry=Stereochemistry(model.stereochemistry) if model.stereochemistry else None,
            structure_status=StructureStatus(model.structure_status),
            registration_status=RegistrationStatus(model.registration_status),
            synthesis_status=SynthesisStatus(model.synthesis_status),
            lifecycle_stage=LifecycleStage(model.lifecycle_stage),
            tags=model.tags,
            invention_date=model.invention_date,
            disclosed_at=model.disclosed_at,
            disclosed_by=model.disclosed_by,
            merged_into_id=model.merged_into_id,
            custom_fields=model.custom_fields,
            originating_org_id=model.originating_org_id,
            identifiers=identifiers,
            mixture_components=mixture_components,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (INSERT)
    # ------------------------------------------------------------------

    def _to_model(self, aggregate: Molecule) -> MoleculeModel:
        model = MoleculeModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            registration_number=aggregate.registration_number.value,
            name=aggregate.name,
            molecule_type=aggregate.molecule_type.value,
            structure_status=aggregate.structure_status.value,
            registration_status=aggregate.registration_status.value,
            synthesis_status=aggregate.synthesis_status.value,
            lifecycle_stage=aggregate.lifecycle_stage.value,
            originating_org_id=aggregate.originating_org_id,
            version=aggregate.version,
        )
        self._set_structure_fields(model, aggregate)
        self._set_optional_fields(model, aggregate)
        model.identifiers = [self._ident_to_model(i, aggregate.workspace_id) for i in aggregate.identifiers]
        model.mixture_components = [self._comp_to_model(c) for c in aggregate.mixture_components]
        return model

    # ------------------------------------------------------------------
    # Mapping: domain aggregate -> SA model (UPDATE)
    # ------------------------------------------------------------------

    def _update_model(self, model: MoleculeModel, aggregate: Molecule) -> None:
        model.name = aggregate.name
        model.molecule_type = aggregate.molecule_type.value
        model.structure_status = aggregate.structure_status.value
        model.registration_status = aggregate.registration_status.value
        model.synthesis_status = aggregate.synthesis_status.value
        model.lifecycle_stage = aggregate.lifecycle_stage.value
        self._set_structure_fields(model, aggregate)
        self._set_optional_fields(model, aggregate)

        # Sync identifiers (replace strategy for simplicity)
        model.identifiers.clear()
        model.identifiers.extend(
            self._ident_to_model(i, aggregate.workspace_id) for i in aggregate.identifiers
        )
        model.mixture_components.clear()
        model.mixture_components.extend(
            self._comp_to_model(c) for c in aggregate.mixture_components
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_structure_fields(model: MoleculeModel, aggregate: Molecule) -> None:
        if aggregate.structure:
            model.smiles = aggregate.structure.smiles
            model.cxsmiles = aggregate.structure.cxsmiles
            model.inchi = aggregate.structure.inchi
            model.inchi_key = aggregate.structure.inchi_key
            model.molfile = aggregate.structure.molfile
        if aggregate.descriptors:
            model.molecular_formula = aggregate.descriptors.molecular_formula
            model.molecular_weight = aggregate.descriptors.molecular_weight
            model.exact_mass = aggregate.descriptors.exact_mass
            model.logp = aggregate.descriptors.logp
            model.tpsa = aggregate.descriptors.tpsa
            model.hbd = aggregate.descriptors.hbd
            model.hba = aggregate.descriptors.hba
            model.rotatable_bonds = aggregate.descriptors.rotatable_bonds
            model.aromatic_rings = aggregate.descriptors.aromatic_rings
            model.ring_count = aggregate.descriptors.ring_count
            model.heavy_atom_count = aggregate.descriptors.heavy_atom_count
            model.ro5_violations = aggregate.descriptors.ro5_violations
        if aggregate.predicted_properties:
            model.logd = aggregate.predicted_properties.logd
            model.pka = aggregate.predicted_properties.pka
            model.logs = aggregate.predicted_properties.logs
            model.prediction_source = aggregate.predicted_properties.prediction_source
            model.predicted_at = aggregate.predicted_properties.predicted_at

    @staticmethod
    def _set_optional_fields(model: MoleculeModel, aggregate: Molecule) -> None:
        model.molecular_formula = aggregate.molecular_formula
        model.stereochemistry = aggregate.stereochemistry.value if aggregate.stereochemistry else None
        model.sequence = aggregate.sequence
        model.structure_image_key = aggregate.structure_image_key
        model.tags = aggregate.tags if aggregate.tags else None
        model.custom_fields = aggregate.custom_fields
        model.invention_date = aggregate.invention_date
        model.disclosed_at = aggregate.disclosed_at
        model.disclosed_by = aggregate.disclosed_by
        model.merged_into_id = aggregate.merged_into_id

    @staticmethod
    def _ident_to_model(ident: MoleculeIdentifier, workspace_id: uuid.UUID) -> MoleculeIdentifierModel:
        return MoleculeIdentifierModel(
            id=ident.id,
            molecule_id=ident.molecule_id,
            workspace_id=workspace_id,
            identifier=ident.identifier,
            identifier_type=ident.identifier_type.value,
            source=ident.source,
            registered_by=ident.registered_by,
        )

    @staticmethod
    def _comp_to_model(comp: MixtureComponent) -> MixtureComponentModel:
        return MixtureComponentModel(
            id=comp.id,
            mixture_molecule_id=comp.mixture_molecule_id,
            component_molecule_id=comp.component_molecule_id,
            stoichiometric_ratio=comp.stoichiometric_ratio,
            role=comp.role.value,
        )

    # ------------------------------------------------------------------
    # Additional query methods
    # ------------------------------------------------------------------

    async def find_by_inchi_key(
        self, workspace_id: uuid.UUID, inchi_key: str
    ) -> Molecule | None:
        stmt = select(MoleculeModel).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.inchi_key == inchi_key,
            MoleculeModel.merged_into_id.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_by_registration_number(
        self, workspace_id: uuid.UUID, reg_number: str
    ) -> Molecule | None:
        stmt = select(MoleculeModel).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.registration_number == reg_number,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_by_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Molecule | None:
        stmt = (
            select(MoleculeModel)
            .join(MoleculeIdentifierModel)
            .where(
                MoleculeModel.workspace_id == workspace_id,
                MoleculeIdentifierModel.identifier == identifier,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        domain = self._to_domain(model)
        self._uow.track(domain)
        return domain

    async def find_identifiers_in_workspace(
        self, workspace_id: uuid.UUID, identifiers: set[str]
    ) -> dict[str, uuid.UUID]:
        """Batch lookup: returns {identifier_value: molecule_id} for all matches."""
        if not identifiers:
            return {}
        stmt = (
            select(
                MoleculeIdentifierModel.identifier,
                MoleculeIdentifierModel.molecule_id,
            )
            .where(
                MoleculeIdentifierModel.workspace_id == workspace_id,
                MoleculeIdentifierModel.identifier.in_(identifiers),
            )
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def find_active(
        self,
        workspace_id: uuid.UUID,
        *,
        filters: dict[str, Any] | None = None,
        search_term: str | None = None,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[Molecule]:
        stmt = select(MoleculeModel).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.merged_into_id.is_(None),
            MoleculeModel.registration_status != RegistrationStatus.PENDING_REVIEW.value,
        )
        if filters:
            if "molecule_type" in filters and filters["molecule_type"]:
                stmt = stmt.where(MoleculeModel.molecule_type == filters["molecule_type"])
            if "lifecycle_stage" in filters and filters["lifecycle_stage"]:
                stmt = stmt.where(MoleculeModel.lifecycle_stage == filters["lifecycle_stage"])
            if "structure_status" in filters and filters["structure_status"]:
                stmt = stmt.where(MoleculeModel.structure_status == filters["structure_status"])

        # Free-text search on name, registration_number, formula, inchi_key,
        # and external identifiers (ChEMBL, CAS, vendor IDs, etc.)
        if search_term:
            like_pattern = f"%{search_term}%"
            # Subquery: molecules that have a matching external identifier
            identifier_subq = (
                select(MoleculeIdentifierModel.molecule_id)
                .where(
                    MoleculeIdentifierModel.workspace_id == workspace_id,
                    MoleculeIdentifierModel.identifier.ilike(like_pattern),
                )
            )
            stmt = stmt.where(
                sa.or_(
                    MoleculeModel.name.ilike(like_pattern),
                    MoleculeModel.registration_number.ilike(like_pattern),
                    MoleculeModel.molecular_formula.ilike(like_pattern),
                    MoleculeModel.inchi_key.ilike(like_pattern),
                    MoleculeModel.id.in_(identifier_subq),
                )
            )

        # Project scoping: None = no filter (admin), [] = unscoped only, [ids] = unscoped + matching
        if project_ids is not None:
            unscoped_subq = (
                select(MoleculeModel.id)
                .where(
                    MoleculeModel.workspace_id == workspace_id,
                    ~MoleculeModel.id.in_(
                        select(molecule_projects.c.molecule_id)
                    ),
                )
            )
            if project_ids:
                scoped_subq = select(molecule_projects.c.molecule_id).where(
                    molecule_projects.c.project_id.in_(project_ids)
                )
                stmt = stmt.where(
                    sa.or_(
                        MoleculeModel.id.in_(unscoped_subq),
                        MoleculeModel.id.in_(scoped_subq),
                    )
                )
            else:
                stmt = stmt.where(MoleculeModel.id.in_(unscoped_subq))

        # Deterministic ordering by PK for stable cursor pagination
        stmt = stmt.order_by(MoleculeModel.id)

        if cursor_id is not None:
            stmt = stmt.where(MoleculeModel.id > cursor_id)

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def next_registration_number(
        self, workspace_id: uuid.UUID
    ) -> RegistrationNumber:
        # Extract numeric suffix from "CV-NNNNN" and find the max.
        # Handles tombstones correctly (they keep their numbers).
        stmt = select(
            func.coalesce(
                func.max(
                    func.cast(
                        func.substr(MoleculeModel.registration_number, 4),
                        sa.Integer,
                    )
                ),
                0,
            )
        ).where(MoleculeModel.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        max_num: int = result.scalar_one()
        return RegistrationNumber(value=f"CV-{max_num + 1:05d}")

    async def search_substructure(
        self, workspace_id: uuid.UUID, smarts: str
    ) -> list[Molecule]:
        """Substructure search using RDKit cartridge mol @> operator.

        Requires the 'rdkit' PostgreSQL extension and a mol column with GiST index.
        Falls back to SMILES-based text match if cartridge is not available.
        """
        stmt = (
            select(MoleculeModel)
            .where(
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
                MoleculeModel.smiles.is_not(None),
                text("mol_from_smiles(smiles) @> mol_from_smarts(:smarts)"),
            )
            .params(smarts=smarts)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def search_by_query(
        self,
        workspace_id: uuid.UUID,
        query: dict[str, Any],
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[Molecule]:
        """Compound search using a structured query dict (text + property + structure criteria).

        Delegates WHERE clause composition to SearchQueryComposer. Handles
        similarity threshold GUC and cursor pagination.
        """
        from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
            compose_criteria,
        )

        # Check for similarity criterion — need to SET threshold
        for criterion in query.get("criteria", []):
            if (
                criterion.get("type") == "structure"
                and criterion.get("search_type") == "similarity"
            ):
                safe_threshold = float(criterion.get("threshold", 0.7))
                await self._session.execute(
                    text(f"SET rdkit.tanimoto_threshold = {safe_threshold}")
                )
                break

        where_clause = compose_criteria(query)

        stmt = select(MoleculeModel).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.merged_into_id.is_(None),
        )

        # Require disclosed structure for structure searches
        has_structure = any(
            c.get("type") == "structure" for c in query.get("criteria", [])
        )
        if has_structure:
            stmt = stmt.where(MoleculeModel.smiles.is_not(None))

        if where_clause is not None:
            stmt = stmt.where(where_clause)

        # Apply project scoping if provided
        if project_ids is not None:
            from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
                _project_clause,
            )
            stmt = stmt.where(_project_clause({"project_ids": [str(p) for p in project_ids]}))

        stmt = stmt.order_by(MoleculeModel.id)
        if cursor_id is not None:
            stmt = stmt.where(MoleculeModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def search_similarity(
        self, workspace_id: uuid.UUID, smiles: str, threshold: float = 0.7
    ) -> list[tuple[Molecule, float]]:
        """Similarity search using pre-computed morgan_bfp with GiST index.

        Uses the RDKit cartridge % operator (Tanimoto) which leverages the
        GiST index on morgan_bfp for sub-second search at 500K compounds.
        """
        # Set Tanimoto threshold for the % operator (session-level GUC).
        # SET does not accept parameterised values in PostgreSQL, so we
        # validate the float and embed it as a literal.
        safe_threshold = float(threshold)
        await self._session.execute(
            text(f"SET rdkit.tanimoto_threshold = {safe_threshold}")
        )

        # Query using % operator (GiST-indexed) + compute exact score
        stmt = (
            select(
                MoleculeModel,
                text(
                    "tanimoto_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q))) AS similarity"
                ),
            )
            .where(
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
                text("morgan_bfp % morganbv_fp(mol_from_smiles(:q))"),
            )
            .params(q=smiles)
            .order_by(text("similarity DESC"))
            .limit(100)
        )
        result = await self._session.execute(stmt)
        return [
            (self._to_domain(row[0]), float(row[1]))
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # Project association methods
    # ------------------------------------------------------------------

    async def add_to_project(
        self, molecule_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Link a molecule to a project (idempotent via ON CONFLICT DO NOTHING)."""
        stmt = (
            pg_insert(molecule_projects)
            .values(molecule_id=molecule_id, project_id=project_id)
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def remove_from_project(
        self, molecule_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Unlink a molecule from a project."""
        stmt = molecule_projects.delete().where(
            molecule_projects.c.molecule_id == molecule_id,
            molecule_projects.c.project_id == project_id,
        )
        await self._session.execute(stmt)

    async def find_project_ids(self, molecule_id: uuid.UUID) -> list[uuid.UUID]:
        """Return all project IDs linked to a given molecule."""
        stmt = select(molecule_projects.c.project_id).where(
            molecule_projects.c.molecule_id == molecule_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
