"""032 — repair orphan dose-response y_readout_name on imported readouts.

Pre-this-fix the CDD mapper emitted ``y_readout_name`` from the source
vault's ``response_readout_definition`` directly. When that CDD readout
was itself the output of a normalization calc (e.g. "% Inhibition" derived
from a raw signal), cellar skipped it from the readout list and lifted
the formula onto the raw input's ``normalizations`` set — leaving the DR
config pointing at a name that no longer existed in the imported
protocol. The state was creatable (``Protocol.create`` doesn't
cross-validate) but ``Protocol.update_readout_definition`` does, so any
attempt to edit such a DR readout in the design tab returned 422.

This migration redirects orphan ``y_readout_name`` references onto the
surviving sibling readout that emits the matching normalization layer
and records ``y_normalization`` so the 4PL fitter consumes the right
layer rather than the raw signal. Rows whose ``y_readout_name`` resolves
fine on a sibling are untouched.

Resolution is heuristic but conservative — we only rewrite when:
  1. The current y_readout_name does not match any sibling readout's name
  2. The name matches one of the known normalization-formula synonyms
  3. Exactly one sibling readout emits that formula

Rows that can't be resolved unambiguously are left alone and emitted as
a NOTICE so the operator can decide.

Revision ID: 032_repair_orphan_dr_y_readout
Revises: 031_cm_curve_snapshot
Create Date: 2026-05-13
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision: str = "032_repair_orphan_dr_y_readout"
down_revision: str | None = "031_cm_curve_snapshot"
branch_labels: None = None
depends_on: None = None


# Map common CDD calc-output readout names to the cellar normalization
# formula they actually represent. Case-insensitive and whitespace-tolerant.
_NAME_TO_FORMULA: dict[str, str] = {
    "% inhibition": "percent_inhibition",
    "percent inhibition": "percent_inhibition",
    "%inhibition": "percent_inhibition",
    "% activation": "percent_activation",
    "percent activation": "percent_activation",
    "%activation": "percent_activation",
    "% control": "percent_control",
    "percent control": "percent_control",
    "%control": "percent_control",
    "z score": "z_score",
    "z-score": "z_score",
    "zscore": "z_score",
}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _name_to_formula(name: str) -> str | None:
    return _NAME_TO_FORMULA.get(_normalize_name(name))


def upgrade() -> None:
    conn = op.get_bind()

    # Pull every DR readout. Set is small even on large deployments (one row
    # per dose-response readout def); no need to stream.
    rows = conn.execute(
        sa.text(
            """
            SELECT id, protocol_id, dose_response_config
            FROM readout_definitions
            WHERE data_type = 'dose_response'
              AND dose_response_config IS NOT NULL
            """
        )
    ).fetchall()

    repaired = 0
    skipped_resolved = 0
    skipped_unresolvable = 0

    for rd_id, protocol_id, cfg in rows:
        # SQLAlchemy returns JSONB as a dict already; defensive-parse if
        # an older driver hands back a str.
        if isinstance(cfg, str):
            cfg = json.loads(cfg)

        y_name = (cfg or {}).get("y_readout_name")
        if not y_name:
            continue

        # Fetch sibling readouts in the same protocol (excluding this row)
        siblings = conn.execute(
            sa.text(
                """
                SELECT name, normalizations
                FROM readout_definitions
                WHERE protocol_id = :pid AND id != :rid
                """
            ),
            {"pid": protocol_id, "rid": rd_id},
        ).fetchall()

        sibling_names = {s.name for s in siblings}
        if y_name in sibling_names:
            skipped_resolved += 1
            continue  # already valid

        formula = _name_to_formula(y_name)
        if formula is None:
            skipped_unresolvable += 1
            print(
                f"NOTICE: readout_definition {rd_id} has orphan "
                f"y_readout_name={y_name!r}; not a known normalization-name "
                "synonym — leaving alone."
            )
            continue

        # Find siblings that emit this formula
        matching = []
        for sib in siblings:
            norms = sib.normalizations
            if isinstance(norms, str):
                norms = json.loads(norms)
            if norms and formula in norms:
                matching.append(sib.name)

        if len(matching) != 1:
            skipped_unresolvable += 1
            print(
                f"NOTICE: readout_definition {rd_id} has orphan "
                f"y_readout_name={y_name!r}; matched {len(matching)} sibling "
                f"readouts emitting {formula!r} — need exactly 1 to rewrite. "
                f"Candidates: {matching}. Leaving alone."
            )
            continue

        # Safe to rewrite — update both y_readout_name and y_normalization.
        # Build the new JSONB with two ``jsonb_set`` calls so we don't have to
        # round-trip the whole config through a placeholder (asyncpg gets
        # confused by ``:cfg::jsonb`` because ``::`` is also its cast token).
        conn.execute(
            sa.text(
                """
                UPDATE readout_definitions
                SET dose_response_config = jsonb_set(
                    jsonb_set(
                        dose_response_config,
                        '{y_readout_name}',
                        to_jsonb(CAST(:new_y AS text))
                    ),
                    '{y_normalization}',
                    to_jsonb(CAST(:formula AS text))
                )
                WHERE id = :rid
                """
            ),
            {"new_y": matching[0], "formula": formula, "rid": rd_id},
        )
        repaired += 1
        print(
            f"REPAIRED: readout_definition {rd_id}: "
            f"y_readout_name {y_name!r} -> {matching[0]!r}, "
            f"y_normalization -> {formula!r}"
        )

    print(
        f"032 summary: repaired={repaired}, "
        f"already_valid={skipped_resolved}, "
        f"unresolvable={skipped_unresolvable}"
    )


def downgrade() -> None:
    # No safe downgrade — the original ``y_readout_name`` references readouts
    # that don't exist in the protocol, so restoring them would re-break the
    # update path. The pre-fix state is recoverable from the CDD source if
    # ever needed.
    pass
