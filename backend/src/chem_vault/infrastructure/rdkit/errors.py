"""RDKit infrastructure errors."""

from chem_vault.domain.shared.errors import DomainError


class InvalidSmilesError(DomainError):
    """Raised when SMILES cannot be parsed."""

    def __init__(self, smiles: str, reason: str = "Failed to parse SMILES") -> None:
        self.smiles = smiles
        super().__init__(f"Invalid SMILES '{smiles}': {reason}")


class StandardizationError(DomainError):
    """Raised when structure standardization fails."""

    def __init__(self, smiles: str, reason: str) -> None:
        self.smiles = smiles
        super().__init__(f"Standardization failed for '{smiles}': {reason}")


class QCRejectedError(DomainError):
    """Raised when QC score exceeds the rejection threshold."""

    def __init__(
        self, smiles: str, score: int, issues: list[str], threshold: int
    ) -> None:
        self.smiles = smiles
        self.score = score
        self.issues = issues
        self.threshold = threshold
        issues_str = "; ".join(issues)
        super().__init__(
            f"QC rejected (score {score} >= threshold {threshold}): {issues_str}"
        )
