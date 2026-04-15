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
    CDD_MOLECULE_ID = "cdd_molecule_id"
    SYNONYM = "synonym"
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


class DisclosureStatus(StrEnum):
    """Status of a disclosure request."""

    PENDING = "pending"
    PROCESSING = "processing"
    DISCLOSED = "disclosed"
    MERGED = "merged"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class DisclosureResolutionType(StrEnum):
    """How a disclosure was resolved."""

    NEW_STRUCTURE = "new_structure"
    MERGED_INTO_EXISTING = "merged_into_existing"


class BulkDisclosureStatus(StrEnum):
    """Status of a bulk disclosure operation."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class MergeReason(StrEnum):
    """Reason for merging two molecules."""

    DISCLOSURE_RESOLVED = "disclosure_resolved"
    MANUAL_MERGE = "manual_merge"
    STRUCTURE_CORRECTION = "structure_correction"
    DUPLICATE_CLEANUP = "duplicate_cleanup"


class BulkRegistrationStatus(StrEnum):
    """Status of a bulk registration operation."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class BulkRegistrationFileFormat(StrEnum):
    """Supported file formats for bulk registration."""

    SDF = "sdf"
    CSV = "csv"
    XLSX = "xlsx"


class CddMoleculeImportStatus(StrEnum):
    """Status of a CDD vault molecule import operation."""

    PENDING = "pending"
    DISCOVERING = "discovering"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class CddImportMode(StrEnum):
    """How molecules are selected for CDD import."""

    FULL_VAULT = "full_vault"
    FILTERED = "filtered"
    SYNC = "sync"


# ---------------------------------------------------------------------------
# Synthesis Route enums
# ---------------------------------------------------------------------------


class RouteType(StrEnum):
    """Topology of a synthesis route."""

    LINEAR = "linear"
    CONVERGENT = "convergent"


class RouteStatus(StrEnum):
    """Lifecycle status of a synthesis route."""

    DRAFT = "draft"
    VALIDATED = "validated"
    PREFERRED = "preferred"
    DEPRECATED = "deprecated"


class RouteScale(StrEnum):
    """Scale of a synthesis route."""

    MILLIGRAM = "milligram"
    GRAM = "gram"
    KILOGRAM = "kilogram"
    PILOT = "pilot"
    PROCESS = "process"


class RouteSource(StrEnum):
    """Origin of a synthesis route."""

    MANUAL = "manual"
    RETROSYNTHETIC_ANALYSIS = "retrosynthetic_analysis"
    LITERATURE = "literature"
    AI_PREDICTED = "ai_predicted"


class ReagentRole(StrEnum):
    """Role of a reagent in a reaction step."""

    REACTANT = "reactant"
    REAGENT = "reagent"
    CATALYST = "catalyst"
    SOLVENT = "solvent"
    BASE = "base"
    LIGAND = "ligand"
