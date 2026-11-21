"""A campaign managed by another app in the realm (e.g. DAIKON makes one campaign per round).

Only the managing app changes the campaign's lifecycle and structure; anyone else is refused.
This is not the campaign lock: a closed campaign refuses everyone, a managed one only refuses
callers that are not its manager. Who the caller is comes from a verified realm token at the
interface; the domain only compares names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from cellar.domain.shared.errors import DataLockedError, ValidationError

MAX_NAME_LENGTH = 100


@dataclass(frozen=True)
class CampaignManagement:
    """Which app manages the campaign, where it lives there, and what to call that app."""

    managed_by: str
    url: str
    label: str

    def __post_init__(self) -> None:
        for field, value in (("managed_by", self.managed_by), ("label", self.label)):
            if not value or not value.strip():
                raise ValidationError(f"Campaign management {field} must not be empty")
            if len(value) > MAX_NAME_LENGTH:
                raise ValidationError(
                    f"Campaign management {field} must be at most {MAX_NAME_LENGTH} characters"
                )
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError("Campaign management url must be an http(s) address")


class CampaignManagedElsewhereError(DataLockedError):
    """A change to a managed campaign by someone other than the managing app."""

    def __init__(self, management: CampaignManagement) -> None:
        self.management = management
        super().__init__(f"This campaign is managed in {management.label}; change it there.")

    def body_extras(self) -> dict[str, Any]:
        return {
            "managed_by": self.management.managed_by,
            "managed_label": self.management.label,
            "managed_url": self.management.url,
        }


def ensure_writable_by(management: CampaignManagement | None, acting_service: str | None) -> None:
    """Refuse a structural change unless the campaign is unmanaged or the caller manages it."""
    if management is not None and acting_service != management.managed_by:
        raise CampaignManagedElsewhereError(management)
