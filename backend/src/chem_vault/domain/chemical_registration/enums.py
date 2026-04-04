"""Chemical registration enums."""

from enum import StrEnum


class MoleculeType(StrEnum):
    """Classification of molecule."""

    SMALL_MOLECULE = "small_molecule"
    PEPTIDE = "peptide"
    BIOLOGIC = "biologic"
    ANTIBODY = "antibody"
    NUCLEIC_ACID = "nucleic_acid"
    MIXTURE = "mixture"
    UNKNOWN = "unknown"


class Stereochemistry(StrEnum):
    """Stereochemical classification."""

    ACHIRAL = "achiral"
    SINGLE_STEREO = "single_stereo"
    MULTI_STEREO = "multi_stereo"
    RACEMIC = "racemic"
    UNDEFINED = "undefined"


class StructureStatus(StrEnum):
    """Whether a molecule's structure has been disclosed."""

    UNDISCLOSED = "undisclosed"
    DISCLOSED = "disclosed"


class RegistrationStatus(StrEnum):
    """Approval status for molecule registration."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class SynthesisStatus(StrEnum):
    """Physical synthesis state of a molecule."""

    VIRTUAL = "virtual"
    DESIGNED = "designed"
    SYNTHESIZED = "synthesized"
    PURCHASED = "purchased"


class LifecycleStage(StrEnum):
    """Drug discovery lifecycle stage."""

    REGISTERED = "registered"
    ACTIVE = "active"
    HIT = "hit"
    LEAD = "lead"
    PRECLINICAL_CANDIDATE = "preclinical_candidate"
    DEVELOPMENT_CANDIDATE = "development_candidate"
    DEPRIORITIZED = "deprioritized"
    ARCHIVED = "archived"


class IdentifierType(StrEnum):
    """Type of external identifier mapped to a molecule."""

    VENDOR_ID = "vendor_id"
    CAS_NUMBER = "cas_number"
    CHEMBL_ID = "chembl_id"
    PUBCHEM_CID = "pubchem_cid"
    INTERNAL_LEGACY = "internal_legacy"
    CUSTOM = "custom"


class ComponentRole(StrEnum):
    """Role of a component within a mixture molecule."""

    ACTIVE = "active"
    COUNTERION = "counterion"
    COFORMER = "coformer"
    OTHER = "other"


class RelationshipType(StrEnum):
    """Semantic relationship between two molecules."""

    METABOLITE_OF = "metabolite_of"
    ANALOG_OF = "analog_of"
    PRODRUG_OF = "prodrug_of"
    SALT_OF = "salt_of"
    ENANTIOMER_OF = "enantiomer_of"
    COMPONENT_OF = "component_of"
