"""Ordering a campaign's result rows by one channel's cell value.

Pure — no I/O, no persistence. The tiers exist because a screening column
holds three different kinds of thing: a measured number, a censored number
("> 100", the response never reached the level within the tested range), and
no number at all (ND, or a cell the chemist excluded). Sorting them together
as if they were all numbers puts an inactive compound next to a potent one,
which is the opposite of what a chemist sorting by potency is asking for.

So: plain numbers first, then censored values ordered among themselves, then
the value-less cells. The tier is always ascending — ND sinks to the bottom
whichever direction the chemist sorts — and only the value flips. This is the
same rule the frontend's ``formatInterceptDisplay`` applies to its
``sortValue``, so a server-ordered page and a client-ordered grid agree.
"""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.shared.aggregation_types import ValueQualifier

#: Cells with no comparable number at all.
_VALUELESS = frozenset({ValueQualifier.ND, ValueQualifier.EXCLUDED})

PLAIN_TIER = 0
CENSORED_TIER = 1
VALUELESS_TIER = 2


def channel_sort_key(
    result: CampaignResult, channel_id: uuid.UUID, *, descending: bool = False
) -> tuple[int, float, str]:
    """Sort key for ``result`` by its measurement on ``channel_id``.

    Returns ``(tier, value, result_id)``. The id tie-breaks so equal values
    can't reorder between two reads of the same page.
    """
    measurement = result.find_measurement(channel_id)
    if (
        measurement is None
        or measurement.value is None
        or measurement.value_qualifier in _VALUELESS
    ):
        tier, value = VALUELESS_TIER, 0.0
    elif measurement.value_qualifier in (ValueQualifier.LT, ValueQualifier.GT):
        tier, value = CENSORED_TIER, measurement.value
    else:
        tier, value = PLAIN_TIER, measurement.value

    return (tier, -value if descending else value, str(result.id))
