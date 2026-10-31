"""
Production Rules Engine & Conflict Resolution Architecture.
Defines formal LHS (Left-Hand Side) condition predicates and RHS (Right-Hand Side) consequence actions.

Certainty handling: when a rule fires, the certainty of every fact it asserts is
    CF(conclusion) = CF(premise) * min(CF(rule), CF(fact as written by the action))
where CF(premise) is the MYCIN conjunction (minimum) of the certainties of the facts the
rule's conditions actually read. Client inputs carry CF 1.0, so rules that only read client
inputs behave exactly as before; rules that build on other inferred facts now inherit
their uncertainty instead of resetting it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.facts import Fact, WorkingMemory
from core.uncertainty import CertaintyFactorEngine


class _AnyValue:
    """Marker: the rule asserts this fact, but its value depends on the profile."""
    def __repr__(self) -> str:
        return "ANY"


ANY = _AnyValue()


@dataclass
class RuleFiringTrace:
    """Audit record generated every time a rule fires."""
    rule_id: str
    domain: str
    description: str
    priority: int
    asserted_facts: list[dict[str, Any]]
    explanation: str
    timestamp: float
    premise_cf: float = 1.0   # certainty of the evidence the rule fired on


@dataclass
class Remedy:
    """
    One counterfactual step: what the client could change to close a gap.

    `changes` maps fact names to the value that closes the gap, so the engine can
    re-run forward chaining and confirm the fix really works instead of trusting text.
    """
    text: str
    changes: dict[str, Any] = field(default_factory=dict)
    fixable: bool = True        # False: not something the client can act on (e.g. age)
    alternative: bool = False   # shown to the client but not part of the verified plan


class _TrackingMemory:
    """Read-only view of working memory that records which facts a condition read."""

    def __init__(self, wm: WorkingMemory):
        self._wm = wm
        self.touched: set = set()

    def _touch(self, name: str) -> None:
        if self._wm.has_fact(name):
            self.touched.add(name)

    def get_value(self, name: str, default: Any = None) -> Any:
        self._touch(name)
        return self._wm.get_value(name, default)

    def get_certainty(self, name: str, default: float = 0.0) -> float:
        self._touch(name)
        return self._wm.get_certainty(name, default)

    def get_fact(self, name: str):
        self._touch(name)
        return self._wm.get_fact(name)

    def has_fact(self, name: str) -> bool:
        self._touch(name)
        return self._wm.has_fact(name)

    def __getattr__(self, item: str):
        return getattr(self._wm, item)


@dataclass
class Rule:
    """
    Formal Production Rule (IF LHS THEN RHS).
    Equipped with Priority (Salience), MYCIN Rule Attenuation ($CF_{rule}$),
    and dependency metadata for Backward Chaining.

    Backward-chaining metadata:
      produces  fact name -> the value this rule asserts (static values only). A name listed
                in consequence_fact_names but absent here is dynamic (value depends on profile).
      remedy    given a working memory where the rule's gate is not satisfied, returns the
                Remedy steps that would satisfy it.
    """
    rule_id: str
    domain: str
    description: str
    priority: int = 100  # Higher integer = higher execution priority in conflict resolution
    conditions: list[Callable[[WorkingMemory], bool]] = field(default_factory=list)
    action: Callable[[WorkingMemory, Rule], list[Fact]] | None = None
    cf_rule: float = 1.0  # Rule certainty multiplier
    condition_descriptions: list[str] = field(default_factory=list)
    consequence_fact_names: list[str] = field(default_factory=list)
    produces: dict[str, Any] = field(default_factory=dict)
    remedy: Callable[[WorkingMemory], list[Remedy]] | None = None

    def evaluate_lhs(self, wm: WorkingMemory) -> bool:
        """Evaluates all Left-Hand-Side conditions against the current Working Memory."""
        if not self.conditions:
            return False
        for condition in self.conditions:
            try:
                if not condition(wm):
                    return False
            except Exception:
                return False
        return True

    def premise_certainty(self, wm: WorkingMemory) -> float:
        """MYCIN conjunction: the weakest fact the conditions relied on (1.0 if none)."""
        tracker = _TrackingMemory(wm)
        for condition in self.conditions:
            try:
                condition(tracker)
            except Exception:
                break
        if not tracker.touched:
            return 1.0
        return max(0.0, min(wm.get_certainty(n, 1.0) for n in tracker.touched))

    def can_produce(self, name: str, value: Any) -> bool:
        """True if firing this rule could leave `name == value` in working memory."""
        if name in self.produces:
            return self.produces[name] == value
        return name in self.consequence_fact_names

    def blocks(self, name: str, value: Any) -> bool:
        """True if this rule asserts `name` with a static value different from `value`."""
        return name in self.produces and self.produces[name] != value

    def execute_rhs(self, wm: WorkingMemory) -> list[Fact]:
        """Fires the RHS action, attenuates each conclusion's CF, and asserts it into memory."""
        if not self.action:
            return []
        premise_cf = self.premise_certainty(wm)   # must be read before the facts are asserted
        new_facts = self.action(wm, self)
        for fact in new_facts:
            rule_cf = min(abs(fact.certainty), abs(self.cf_rule))
            if fact.certainty < 0:
                rule_cf = -rule_cf
            fact.certainty = CertaintyFactorEngine.attenuate(premise_cf, rule_cf)
            wm.assert_fact(fact)
        return new_facts
