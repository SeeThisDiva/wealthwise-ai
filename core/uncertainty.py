"""
Uncertainty Reasoning Engine — MYCIN Certainty Factor Calculus
Implements formal Measure of Belief (MB), Measure of Disbelief (MD),
and the classic MYCIN combining function for co-occurring rule evidence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CertaintyValue:
    """Represents an evidence belief degree bounded between -1.0 and +1.0."""
    cf: float  # -1.0 (definitely false) to +1.0 (definitely true)
    mb: float = 0.0  # Measure of Belief [0.0, 1.0]
    md: float = 0.0  # Measure of Disbelief [0.0, 1.0]

    def __post_init__(self):
        # Clamp to [-1.0, +1.0]
        self.cf = max(-1.0, min(1.0, float(self.cf)))
        if self.mb == 0.0 and self.md == 0.0:
            if self.cf >= 0:
                self.mb = self.cf
                self.md = 0.0
            else:
                self.mb = 0.0
                self.md = abs(self.cf)

    @property
    def percentage(self) -> int:
        """Converts certainty into an intuitive 0-100% confidence gauge."""
        return int(round(max(0.0, self.cf) * 100))

    @property
    def label(self) -> str:
        if self.cf >= 0.85:
            return "Definite / High Confidence"
        elif self.cf >= 0.60:
            return "Strong Evidence"
        elif self.cf >= 0.30:
            return "Moderate Evidence"
        elif self.cf > 0.0:
            return "Weak Evidence"
        elif self.cf == 0.0:
            return "Neutral / Insufficient Data"
        else:
            return "Counter-Indicated / Negative"


class CertaintyFactorEngine:
    """Stanford MYCIN combination calculus for expert systems."""

    @staticmethod
    def combine(cf1: float, cf2: float) -> float:
        """
        Combines two independent certainty factors for the same hypothesis:
        
        If cf1 >= 0 and cf2 >= 0:
            cf = cf1 + cf2 * (1 - cf1)
        If cf1 < 0 and cf2 < 0:
            cf = cf1 + cf2 * (1 + cf1)
        If cf1 * cf2 < 0 (opposite signs):
            cf = (cf1 + cf2) / (1 - min(|cf1|, |cf2|))
        """
        cf1 = max(-1.0, min(1.0, float(cf1)))
        cf2 = max(-1.0, min(1.0, float(cf2)))

        if cf1 >= 0 and cf2 >= 0:
            combined = cf1 + cf2 * (1.0 - cf1)
        elif cf1 < 0 and cf2 < 0:
            combined = cf1 + cf2 * (1.0 + cf1)
        else:
            denominator = 1.0 - min(abs(cf1), abs(cf2))
            if denominator == 0.0:
                combined = 0.0
            else:
                combined = (cf1 + cf2) / denominator

        return max(-1.0, min(1.0, round(combined, 4)))

    @classmethod
    def combine_many(cls, cf_list: list[float]) -> float:
        """Accumulates an arbitrary sequence of evidence factors."""
        if not cf_list:
            return 0.0
        acc = cf_list[0]
        for next_cf in cf_list[1:]:
            acc = cls.combine(acc, next_cf)
        return acc

    @staticmethod
    def attenuate(cf_premise: float, cf_rule: float) -> float:
        """
        Applies rule attenuation (inference propagation):
        CF(hypothesis) = CF(premise) * CF(rule)
        """
        return max(-1.0, min(1.0, round(cf_premise * cf_rule, 4)))
