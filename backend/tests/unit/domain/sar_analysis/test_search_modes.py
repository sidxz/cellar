import pytest

from chem_vault.domain.sar_analysis.search_modes import (
    MODE_DEFAULTS,
    ModeConfig,
    SearchMode,
)
from chem_vault.domain.sar_analysis.similarity_metric import Tanimoto, Tversky


def test_three_modes_exist() -> None:
    assert {m.value for m in SearchMode} == {"similar", "scaffold_hop", "fragment_in_target"}


@pytest.mark.parametrize(
    "mode,algorithm,metric_type,threshold",
    [
        (SearchMode.SIMILAR, "morgan", Tanimoto, 0.7),
        (SearchMode.SCAFFOLD_HOP, "fcfp", Tanimoto, 0.55),
        (SearchMode.FRAGMENT_IN_TARGET, "morgan", Tversky, 0.7),
    ],
)
def test_mode_defaults(
    mode: SearchMode, algorithm: str, metric_type: type, threshold: float
) -> None:
    config: ModeConfig = MODE_DEFAULTS[mode]
    assert config.algorithm == algorithm
    assert isinstance(config.metric, metric_type)
    assert config.threshold == threshold


def test_fragment_in_target_uses_tversky_alpha_one_beta_zero() -> None:
    config = MODE_DEFAULTS[SearchMode.FRAGMENT_IN_TARGET]
    assert isinstance(config.metric, Tversky)
    assert config.metric.alpha == 1.0
    assert config.metric.beta == 0.0
