"""Unit test: migration 074 build_stage_rows — one campaign_stage row per
existing campaign_channel.hit_threshold. Pure function, no DB.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

_M074_PATH = (
    Path(__file__).resolve().parents[4] / "alembic" / "versions" / "074_campaign_hit_stages.py"
)


def _load_m074() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m074", _M074_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _channel_row(
    *,
    id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    label: str = "IC50",
    display_order: int = 0,
    hit_threshold: dict | None = None,
) -> dict:
    return {
        "id": id or uuid.uuid4(),
        "campaign_id": campaign_id or uuid.uuid4(),
        "label": label,
        "display_order": display_order,
        "hit_threshold": hit_threshold,
    }


_LT_5 = {"readout_name": "x", "operator": "lt", "value": 5.0}


def test_none_threshold_is_skipped() -> None:
    m074 = _load_m074()
    assert m074.build_stage_rows([_channel_row(hit_threshold=None)]) == []


def test_in_operator_is_skipped() -> None:
    m074 = _load_m074()
    rows = [_channel_row(hit_threshold={"readout_name": "x", "operator": "in", "value": ["a"]})]
    assert m074.build_stage_rows(rows) == []


def test_between_operator_keeps_value_array() -> None:
    m074 = _load_m074()
    channel_id = uuid.uuid4()
    rows = [
        _channel_row(
            id=channel_id,
            hit_threshold={"readout_name": "x", "operator": "between", "value": [1.0, 2.0]},
        )
    ]
    out = m074.build_stage_rows(rows)
    assert len(out) == 1
    assert out[0]["criteria"] == [
        {"channel_id": str(channel_id), "operator": "between", "value": [1.0, 2.0]}
    ]


def test_name_is_label_plus_hits() -> None:
    m074 = _load_m074()
    rows = [_channel_row(label="IC50", hit_threshold=_LT_5)]
    out = m074.build_stage_rows(rows)
    assert out[0]["name"] == "IC50 hits"


def test_collisions_within_campaign_are_suffixed_case_insensitively() -> None:
    m074 = _load_m074()
    campaign_id = uuid.uuid4()
    rows = [
        _channel_row(campaign_id=campaign_id, label="IC50", hit_threshold=_LT_5),
        _channel_row(campaign_id=campaign_id, label="ic50", hit_threshold=_LT_5),
        _channel_row(campaign_id=campaign_id, label="IC50", hit_threshold=_LT_5),
    ]
    out = m074.build_stage_rows(rows)
    assert [r["name"] for r in out] == ["IC50 hits", "ic50 hits (2)", "IC50 hits (3)"]


def test_collisions_are_scoped_per_campaign() -> None:
    m074 = _load_m074()
    rows = [
        _channel_row(label="IC50", hit_threshold=_LT_5),
        _channel_row(label="IC50", hit_threshold=_LT_5),  # different campaign_id (default)
    ]
    out = m074.build_stage_rows(rows)
    assert [r["name"] for r in out] == ["IC50 hits", "IC50 hits"]


def test_display_order_parent_stage_id_and_id_shape() -> None:
    m074 = _load_m074()
    rows = [_channel_row(display_order=3, hit_threshold=_LT_5)]
    out = m074.build_stage_rows(rows)
    assert out[0]["display_order"] == 3
    assert out[0]["parent_stage_id"] is None
    assert isinstance(out[0]["id"], uuid.UUID)


def test_ordering_preserves_input_row_order() -> None:
    m074 = _load_m074()
    rows = [
        _channel_row(label="B", display_order=1, hit_threshold=_LT_5),
        _channel_row(label="A", display_order=0, hit_threshold=_LT_5),
    ]
    out = m074.build_stage_rows(rows)
    assert [r["name"] for r in out] == ["B hits", "A hits"]
    assert [r["display_order"] for r in out] == [1, 0]
