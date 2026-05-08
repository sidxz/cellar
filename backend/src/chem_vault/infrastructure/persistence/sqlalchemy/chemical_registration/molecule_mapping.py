"""Pure model→domain mapping for Molecule.

Extracted from ``SQLAlchemyMoleculeRepository`` so that both the write-side
repository and the read-side ``SQLAlchemyMoleculeReader`` can produce
``Molecule`` aggregates without duplicating the mapping logic.
"""

from __future__ import annotations

from chem_vault.domain.chemical_registration.enums import (
    ComponentRole,
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
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)


def model_to_molecule(model: MoleculeModel) -> Molecule:
    """Map an SA ``MoleculeModel`` into the ``Molecule`` aggregate."""
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
            identifier_type=ident.identifier_type,
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
        morgan_fp=model.fp_morgan,
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
