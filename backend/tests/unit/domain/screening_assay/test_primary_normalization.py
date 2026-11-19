"""The default layer of a readout is the same in every process: first in sorted order."""

import subprocess
import sys

from cellar.domain.screening_assay.enums import ReadoutNormalization, primary_normalization

_PROBE = (
    "from cellar.domain.screening_assay.enums import ReadoutNormalization as N, "
    "primary_normalization; "
    "print(primary_normalization(frozenset({N.Z_SCORE, N.PERCENT_INHIBITION})))"
)


def test_picks_the_first_layer_in_sorted_order() -> None:
    layers = frozenset({ReadoutNormalization.Z_SCORE, ReadoutNormalization.PERCENT_INHIBITION})
    assert primary_normalization(layers) == "percent_inhibition"


def test_ignores_none() -> None:
    assert primary_normalization(frozenset({ReadoutNormalization.NONE})) is None


def test_is_the_same_whatever_the_hash_seed() -> None:
    picks = {
        subprocess.run(  # noqa: S603 — fixed argv: this interpreter and a constant probe
            [sys.executable, "-c", _PROBE],
            env={"PYTHONHASHSEED": str(seed)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in range(6)
    }
    assert picks == {"percent_inhibition"}
