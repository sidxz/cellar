"""CreateBatch refuses values outside its lists instead of raising."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from returns.result import Failure

from cellar.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from cellar.domain.shared.errors import ValidationError


@pytest.mark.parametrize(
    "patch",
    [{"amount_unit": "µg"}, {"source": "Enamine"}, {"concentration_unit": "ppm"}],
)
async def test_unknown_listed_value_is_a_validation_failure(patch: dict) -> None:
    fields = {"source": "synthesized", "amount_unit": "mg", "concentration_value": 1.0, **patch}
    cmd = CreateBatchCommand(
        workspace_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
        chemist=uuid.uuid4(),
        amount_value=1.0,
        **fields,
    )
    uc = CreateBatch(
        uow=MagicMock(), repo=MagicMock(), molecule_repo=MagicMock(), dispatcher=MagicMock()
    )
    result = await uc(cmd)
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
