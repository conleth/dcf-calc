from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ScenarioProfile:
    name: str
    growth_rates: List[float]
    terminal_multiple: float
    probability: float = 0.33


@dataclass
class ScenarioValuation:
    name: str
    intrinsic_value: float
    buy_price: float
    upside: float
    downside: float
    margin_of_safety_pct: float
    effective_growth_rates: List[float]
    terminal_multiple: float
    cashflows: List[float]
    discounted_cashflows: List[float]
    terminal_value: float
    discounted_terminal_value: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class AggregateValuation:
    scenario_results: List[ScenarioValuation]
    weighted_intrinsic_value: float
    margin_of_safety_buy_price: float
    current_price: float
    metadata: Dict[str, float]
    warnings: List[str] = field(default_factory=list)


class DiscountedCashFlowModel:
    def __init__(self, discount_rate: float, margin_of_safety: float) -> None:
        self.discount_rate = max(discount_rate, 0.0)
        self.margin_of_safety = max(min(margin_of_safety, 0.99), 0.0)

    def evaluate(
        self,
        base_cashflow: float,
        current_price: float,
        shares_outstanding: float,
        scenarios: List[ScenarioProfile],
    ) -> AggregateValuation:
        per_share = base_cashflow / shares_outstanding if shares_outstanding else base_cashflow
        results: List[ScenarioValuation] = []
        warnings: List[str] = []
        for scenario in scenarios:
            valuation = self._evaluate_scenario(per_share, current_price, scenario)
            results.append(valuation)
            warnings.extend(valuation.warnings)

        total_probability = sum(s.probability for s in scenarios)
        if total_probability <= 0:
            probabilities = [1 / len(scenarios) for _ in scenarios]
        else:
            probabilities = [s.probability / total_probability for s in scenarios]

        weighted_intrinsic = sum(v.intrinsic_value * p for v, p in zip(results, probabilities))
        buy_price = weighted_intrinsic * (1 - self.margin_of_safety)

        return AggregateValuation(
            scenario_results=results,
            weighted_intrinsic_value=weighted_intrinsic,
            margin_of_safety_buy_price=buy_price,
            current_price=current_price,
            metadata={"discount_rate": self.discount_rate, "margin_of_safety": self.margin_of_safety},
            warnings=list(dict.fromkeys(warnings)),
        )

    def _evaluate_scenario(
        self,
        base_cashflow_per_share: float,
        current_price: float,
        scenario: ScenarioProfile,
    ) -> ScenarioValuation:
        years = len(scenario.growth_rates)
        if years == 0:
            raise ValueError("Growth rates are required for at least one forecast year.")

        cashflows: List[float] = []
        discounted: List[float] = []
        value = base_cashflow_per_share
        warnings: List[str] = []
        for idx, rate in enumerate(scenario.growth_rates, start=1):
            value = value * (1 + rate)
            cashflows.append(value)
            discounted_value = value / ((1 + self.discount_rate) ** idx)
            discounted.append(discounted_value)
            if rate > 0.15:
                warnings.append(f"{scenario.name}: Growth rate {rate:.0%} exceeds conservative range.")
            if rate < -0.1:
                warnings.append(f"{scenario.name}: Growth rate {rate:.0%} implies steep decline.")

        terminal_value = cashflows[-1] * scenario.terminal_multiple
        discounted_terminal = terminal_value / ((1 + self.discount_rate) ** years)

        intrinsic_value = sum(discounted) + discounted_terminal
        buy_price = intrinsic_value * (1 - self.margin_of_safety)
        upside = (intrinsic_value / current_price - 1) if current_price else 0.0
        downside = (buy_price / current_price - 1) if current_price else 0.0
        if scenario.terminal_multiple > 20:
            warnings.append(f"{scenario.name}: Terminal multiple {scenario.terminal_multiple:.1f} is aggressive.")
        if scenario.terminal_multiple < 5:
            warnings.append(f"{scenario.name}: Terminal multiple {scenario.terminal_multiple:.1f} is unusually low.")

        return ScenarioValuation(
            name=scenario.name,
            intrinsic_value=intrinsic_value,
            buy_price=buy_price,
            upside=upside,
            downside=downside,
            margin_of_safety_pct=self.margin_of_safety,
            effective_growth_rates=scenario.growth_rates,
            terminal_multiple=scenario.terminal_multiple,
            cashflows=cashflows,
            discounted_cashflows=discounted,
            terminal_value=terminal_value,
            discounted_terminal_value=discounted_terminal,
            warnings=list(dict.fromkeys(warnings)),
        )


class DividendDiscountModel(DiscountedCashFlowModel):
    pass
