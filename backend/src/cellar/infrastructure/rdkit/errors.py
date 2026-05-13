"""RDKit infrastructure errors."""

from cellar.domain.shared.errors import DomainError, ValidationError


class InvalidSmilesError(ValidationError):
    """Raised when SMILES cannot be parsed.

    This is bad user input, so it maps to HTTP 422 via ``ValidationError``.
    """

    def __init__(self, smiles: str, reason: str = "Failed to parse SMILES") -> None:
        self.smiles = smiles
        super().__init__(f"Invalid SMILES '{smiles}': {reason}")


class StandardizationError(ValidationError):
    """Raised when structure standardization fails (e.g. InChI generation).

    Maps to HTTP 422 — the input is structurally invalid even though it
    parsed as SMILES.
    """

    def __init__(self, smiles: str, reason: str) -> None:
        self.smiles = smiles
        super().__init__(f"Standardization failed for '{smiles}': {reason}")


class QCRejectedError(DomainError):
    """Raised when QC score exceeds the rejection threshold."""

    def __init__(self, smiles: str, score: int, issues: list[str], threshold: int) -> None:
        self.smiles = smiles
        self.score = score
        self.issues = issues
        self.threshold = threshold
        issues_str = "; ".join(issues)
        super().__init__(f"QC rejected (score {score} >= threshold {threshold}): {issues_str}")
