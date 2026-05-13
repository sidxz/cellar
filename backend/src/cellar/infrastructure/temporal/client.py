"""Temporal client factory."""

from __future__ import annotations

from temporalio.client import Client

from cellar.infrastructure.temporal.settings import TemporalSettings


async def create_temporal_client(settings: TemporalSettings) -> Client:
    """Connect to the Temporal server and return a client instance."""
    return await Client.connect(
        settings.address,
        namespace=settings.namespace,
    )
