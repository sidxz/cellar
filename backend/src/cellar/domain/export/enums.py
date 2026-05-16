from __future__ import annotations
from enum import StrEnum


class ExportFormat(StrEnum):
    CSV = "csv"
    SDF = "sdf"
    XLSX = "xlsx"
    PDF = "pdf"

    @property
    def extension(self) -> str:
        return f".{self.value}"

    @property
    def media_type(self) -> str:
        return {
            ExportFormat.CSV: "text/csv",
            ExportFormat.SDF: "chemical/x-sdf",
            ExportFormat.XLSX: (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            ExportFormat.PDF: "application/pdf",
        }[self]


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ExportSource(StrEnum):
    SEARCH = "search"
    # Future: RUNS, BATCHES, ACTIVITY, COLLECTION, ELN
