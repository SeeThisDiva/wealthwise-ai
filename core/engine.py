"""
Inference Engine: Forward Chaining and Backward Chaining (Goal-Seek / Counterfactuals).
Provides deterministic symbolic reasoning, conflict resolution, cycle avoidance,
and actionable counterfactual explanations for rejected financial targets.
"""

from __future__ import annotations

import time
from typing import Any

from core.facts import Fact, WorkingMemory
from core.rules import Remedy, Rule, RuleFiringTrace


class InferenceEngine:
    """
    Production Rule Inference Engine.
    Executes Forward Chaining for comprehensive advisory discovery,
    and Backward Chaining for goal-directed counterfactual remediation.
    """

    def __init__(self, working_memory: WorkingMemory | None = None):
        self.wm = working_memory if working_memory is not None else WorkingMemory()
        self.rules: list[Rule] = []
        self.firing_history: list[RuleFiringTrace] = []
        # Categorical inputs the counterfactual search may vary one at a time,
        # e.g. {"user.risk_tolerance": ["Low", "Medium", "High"]}. Set by the orchestrator.
        self.counterfactual_space: dict[str, list[Any]] = {}

    def register_rule(self, rule: Rule) -> None:
        """Adds a rule to the system's rule base."""
        self.rules.append(rule)

    def register_rules(self, rules: list[Rule]) -> None:
        """Batch registers multiple production rules."""
        self.rules.extend(rules)

    # ==========================================================================
    # 1. Forward Chaining (Data-Driven Discovery)
    # ==========================================================================

    def forward_chain(self, max_cycles: int = 50) -> list[RuleFiringTrace]:
        """
        Executes Forward Chaining Match-Resolve-Act loop:
        1. MATCH: Identify all rules whose LHS evaluate to True in current WM.
        2. RESOLVE: Order candidate rules by Priority (Salience) descending.
        3. ACT: Fire top-priority rule, assert facts, mark rule as fired.
        Repeats until no new rules can fire (quiescence) or cycle limit reached.
        """
        fired_rule_ids: set[str] = set()
        self.firing_history.clear()

        for _cycle in range(max_cycles):
            candidates: list[Rule] = []

            # 1. Match Phase
            for rule in self.rules:
                if rule.rule_id in fired_rule_ids:
                    continue  # Rule already fired in this session (refraction)
                if rule.evaluate_lhs(self.wm):
                    candidates.append(rule)

            if not candidates:
                # Quiescence reached: no more rules can fire
                break

            # 2. Conflict Resolution: Sort by Priority (Salience) descending
            candidates.sort(key=lambda r: r.priority, reverse=True)

            # 3. Act Phase: Fire the selected rule
            selected_rule = candidates[0]
            fired_rule_ids.add(selected_rule.rule_id)

            premise_cf = selected_rule.premise_certainty(self.wm)
            new_facts = selected_rule.execute_rhs(self.wm)

            trace = RuleFiringTrace(
                rule_id=selected_rule.rule_id,
                domain=selected_rule.domain,
                description=selected_rule.description,
                priority=selected_rule.priority,
                asserted_facts=[f.to_dict() for f in new_facts],
                explanation=selected_rule.description,
                timestamp=time.time(),
                premise_cf=premise_cf
            )
            self.firing_history.append(trace)

        return self.firing_history

    # ==========================================================================
    # 2. Backward Chaining (Goal-Directed Reasoning & Counterfactual Explanations)
    # ==========================================================================

    def _initial_facts(self) -> dict[str, Fact]:
        """The client-asserted facts: the only inputs a counterfactual may change."""
        return {n: f for n, f in self.wm.all_facts().items() if f.source == "initial"}

    @staticmethod
    def _memory_from(base: dict[str, Fact], changes: dict[str, Any]) -> WorkingMemory:
        wm = WorkingMemory()
        for name, f in base.items():
            wm.assert_fact(Fact(
                name=name, value=changes.get(name, f.value), certainty=f.certainty,
                domain=f.domain, source=f.source, explanation=f.explanation
            ))
        return wm

    def _simulate(self, base: dict[str, Fact], changes: dict[str, Any]) -> WorkingMemory:
        """Re-runs forward chaining on the client's facts with `changes` applied."""
        wm = self._memory_from(base, changes)
        sim = InferenceEngine(wm)
        sim.rules = self.rules
        sim.forward_chain()
        return wm

    def _single_change_search(
        self, base: dict[str, Fact], target: str, desired: Any
    ) -> list[Remedy]:
        """Finds one-input changes (from counterfactual_space) that make the goal true."""
        found: list[Remedy] = []
        for fact_name, options in self.counterfactual_space.items():
            if fact_name not in base:
                continue
            current = base[fact_name].value
            for option in options:
                if option == current:
                    continue
                if self._simulate(base, {fact_name: option}).get_value(target) == desired:
                    label = fact_name.split(".", 1)[-1].replace("_", " ")
                    found.append(Remedy(
                        text=f"Changing {label} from '{current}' to '{option}' would give "
                             f"{target} = {desired}.",
                        changes={fact_name: option}
                    ))
        return found

    def backward_chain_goal(
        self,
        target_fact_name: str,
        desired_value: Any
    ) -> dict[str, Any]:
        """
        Backward Chaining Goal-Seek.

        1. Find the rules that can assert `target = desired` (candidates) and the rules that
           assert a conflicting static value (blockers).
        2. Evaluate those rules against the client's own facts. A blocker whose LHS holds, or a
           candidate whose LHS fails, is a gap; the rule's `remedy` says how to close it.
           Fixes are applied cumulatively so later gaps see earlier fixes.
        3. Re-run forward chaining with the proposed changes. The plan is reported as
           `plan_verified` only if the goal is then really asserted, so the advice cannot
           drift away from what the rules actually do.
        """
        target, desired = target_fact_name, desired_value
        current_val = self.wm.get_value(target)
        base_result = {
            "target": target,
            "desired_value": desired,
            "current_value": current_val,
        }

        if current_val == desired:
            return {**base_result, "achieved": True, "remediation_plan": [], "plan_verified": True,
                    "verified_changes": {}, "rule_analyses": [],
                    "message": f"Goal '{target} = {desired}' is currently ALREADY SATISFIED."}

        base = self._initial_facts()
        if not base:
            return {**base_result, "achieved": False, "remediation_plan": [], "plan_verified": False,
                    "verified_changes": {}, "rule_analyses": [],
                    "message": "No client profile is loaded; run an analysis before seeking a goal."}

        candidates = sorted((r for r in self.rules if r.can_produce(target, desired)),
                            key=lambda r: r.priority, reverse=True)
        if not candidates:
            return {**base_result, "achieved": False, "remediation_plan": [], "plan_verified": False,
                    "verified_changes": {}, "rule_analyses": [],
                    "message": f"No inference rules found capable of asserting '{target} = {desired}'."}

        blockers = sorted((r for r in self.rules if r.blocks(target, desired)),
                          key=lambda r: r.priority, reverse=True)

        best: dict[str, Any] | None = None
        analyses: list[dict[str, Any]] = []

        for cand in candidates:
            applied: dict[str, Any] = {}
            steps: list[Remedy] = []
            path: list[dict[str, Any]] = []

            for rule in blockers + [cand]:
                is_blocker = rule is not cand
                wm = self._memory_from(base, applied)
                if is_blocker:
                    gap = rule.evaluate_lhs(wm)
                else:
                    # Only judge a candidate that knows how to explain itself; rules that
                    # depend on other derived facts are checked by the simulation below.
                    gap = rule.remedy is not None and not rule.evaluate_lhs(wm)
                if not gap:
                    continue

                remedies = rule.remedy(wm) if rule.remedy else []
                for rem in remedies:
                    if rem.fixable and not rem.alternative:
                        applied.update(rem.changes)
                steps.extend(remedies)
                path.append({
                    "rule_id": rule.rule_id,
                    "description": rule.description,
                    "role": "blocker" if is_blocker else "requirement",
                    "unmet_conditions": (
                        [rule.description] if is_blocker else list(rule.condition_descriptions)
                    ),
                    "suggested_fixes": [r.text for r in remedies],
                })

            if not path:
                # Nothing is blocking and the rule can fire, yet the value differs:
                # the value depends on the profile, so search single-input changes.
                searched = self._single_change_search(base, target, desired)
                if searched:
                    steps = searched
                    applied = dict(searched[0].changes)
                    path.append({
                        "rule_id": cand.rule_id,
                        "description": cand.description,
                        "role": "counterfactual_search",
                        "unmet_conditions": [f"{target} currently evaluates to {current_val!r}"],
                        "suggested_fixes": [r.text for r in searched],
                    })

            fixable = all(r.fixable for r in steps)
            verified = False
            if path and fixable and applied:
                verified = self._simulate(base, applied).get_value(target) == desired

            entry = {"candidate": cand.rule_id, "steps": steps, "applied": applied,
                     "verified": verified, "fixable": fixable, "path": path}
            analyses.extend(path)
            # Prefer verified plans, then fewer steps.
            rank = (not verified, not fixable, len(steps))
            if path and (best is None or rank < best["rank"]):
                best = {**entry, "rank": rank}

        if best is None:
            return {**base_result, "achieved": False, "remediation_plan": [], "plan_verified": False,
                    "verified_changes": {}, "rule_analyses": analyses,
                    "message": (f"'{target} = {desired}' is not currently asserted, but no change "
                                f"to the client's inputs that the engine can test would produce it.")}

        plan_text = [r.text for r in best["steps"]]
        if best["verified"]:
            message = ("Target goal is currently unachieved. Applying the changes below and "
                       "re-running the rules does achieve it.")
        elif not best["fixable"]:
            message = ("Target goal is currently unachieved, and at least one blocking condition "
                       "(for example age) cannot be changed by the applicant.")
        else:
            message = ("Target goal is currently unachieved. The steps below address the gaps "
                       "found, but re-running the rules did not confirm they are sufficient.")

        return {
            **base_result,
            "achieved": False,
            "remediation_plan": plan_text,
            "plan_verified": best["verified"],
            "verified_changes": best["applied"] if best["verified"] else {},
            "rule_analyses": analyses,
            "message": message,
        }
