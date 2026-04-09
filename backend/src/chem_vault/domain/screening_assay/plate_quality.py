"""PlateQualityCalculator — Z-prime factor computation from plate controls."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class PlateQualityResult:
    """Result of Z-prime calculation for a plate."""
    z_prime: float
    classification: str  # "excellent", "marginal", "poor", "insufficient_data"
    positive_control_mean: float
    positive_control_sd: float
    negative_control_mean: float
    negative_control_sd: float
    signal_to_background: float


class PlateQualityCalculator:
    """Computes Z-prime factor from positive and negative control well values.

    Z' = 1 - (3 * SD_pos + 3 * SD_neg) / |mean_pos - mean_neg|
    """

    def compute(
        self,
        positive_values: list[float],
        negative_values: list[float],
    ) -> PlateQualityResult:
        if len(positive_values) < 2 or len(negative_values) < 2:
            return PlateQualityResult(
                z_prime=0.0,
                classification="insufficient_data",
                positive_control_mean=statistics.mean(positive_values) if positive_values else 0.0,
                positive_control_sd=0.0,
                negative_control_mean=statistics.mean(negative_values) if negative_values else 0.0,
                negative_control_sd=0.0,
                signal_to_background=0.0,
            )

        pos_mean = statistics.mean(positive_values)
        pos_sd = statistics.stdev(positive_values)
        neg_mean = statistics.mean(negative_values)
        neg_sd = statistics.stdev(negative_values)

        separation = abs(pos_mean - neg_mean)
        s2b = neg_mean / pos_mean if pos_mean != 0 else 0.0

        if separation == 0:
            z_prime = 0.0
        else:
            z_prime = 1.0 - (3.0 * pos_sd + 3.0 * neg_sd) / separation

        if z_prime >= 0.5:
            classification = "excellent"
        elif z_prime >= 0.0:
            classification = "marginal"
        else:
            classification = "poor"

        return PlateQualityResult(
            z_prime=z_prime,
            classification=classification,
            positive_control_mean=pos_mean,
            positive_control_sd=pos_sd,
            negative_control_mean=neg_mean,
            negative_control_sd=neg_sd,
            signal_to_background=s2b,
        )
