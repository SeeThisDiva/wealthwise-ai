"""
Working Memory & Fact Base Architecture for the Expert System.
Stores asserted facts, handles dynamic inference assertions, and supports fact queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.uncertainty import CertaintyFactorEngine


@dataclass
class Fact:
    """A single atomic unit of knowledge in the Expert System's Working Memory."""
    name: str
    value: Any
    certainty: float = 1.0  # MYCIN Certainty Factor (-1.0 to 1.0)
    domain: str = "general" # profile | loan | insurance | investment | credit | scoring
    source: str = "initial" # initial | inferred | counterfactual
    explanation: str = ""

    def __post_init__(self):
        self.certainty = max(-1.0, min(1.0, float(self.certainty)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "certainty": self.certainty,
            "domain": self.domain,
            "source": self.source,
            "explanation": self.explanation
        }


class WorkingMemory:
    """
    Dynamic Working Memory (Fact Base).
    Maintains current system state during inference cycles.
    """

    def __init__(self):
        self._facts: dict[str, Fact] = {}
        self._history: list[dict[str, Any]] = []

    def assert_fact(self, fact: Fact) -> None:
        """
        Asserts a fact into working memory.
        If fact already exists with the same name and value, combines Certainty Factors using MYCIN.
        """
        existing = self._facts.get(fact.name)
        if existing and existing.value == fact.value:
            # Combine evidence certainty
            combined_cf = CertaintyFactorEngine.combine(existing.certainty, fact.certainty)
            existing.certainty = combined_cf
            existing.explanation += f" | {fact.explanation}" if fact.explanation else ""
            self._history.append({
                "action": "COMBINE_FACT",
                "name": fact.name,
                "value": fact.value,
                "new_cf": combined_cf
            })
        else:
            self._facts[fact.name] = fact
            self._history.append({
                "action": "ASSERT_FACT",
                "name": fact.name,
                "value": fact.value,
                "cf": fact.certainty
            })

    def retract_fact(self, name: str) -> bool:
        """Removes a fact from working memory."""
        if name in self._facts:
            del self._facts[name]
            self._history.append({"action": "RETRACT_FACT", "name": name})
            return True
        return False

    def get_fact(self, name: str) -> Fact | None:
        """Retrieves a fact by exact identifier."""
        return self._facts.get(name)

    def get_value(self, name: str, default: Any = None) -> Any:
        """Directly returns the value of a fact if present."""
        fact = self._facts.get(name)
        return fact.value if fact is not None else default

    def get_certainty(self, name: str, default: float = 0.0) -> float:
        """Returns the certainty factor of a fact."""
        fact = self._facts.get(name)
        return fact.certainty if fact is not None else default

    def has_fact(self, name: str) -> bool:
        """Returns True if the fact is present in memory."""
        return name in self._facts

    def query_by_domain(self, domain: str) -> list[Fact]:
        """Returns all facts belonging to a specific domain."""
        return [f for f in self._facts.values() if f.domain == domain]

    def all_facts(self) -> dict[str, Fact]:
        """Returns a snapshot copy of all asserted facts."""
        return dict(self._facts)

    def snapshot(self) -> dict[str, Any]:
        """Serializes working memory for hashing or display."""
        return {k: v.to_dict() for k, v in self._facts.items()}

    def clear(self) -> None:
        """Resets working memory."""
        self._facts.clear()
        self._history.clear()
