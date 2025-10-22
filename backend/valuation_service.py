from __future__ import annotations

from typing import Any, Dict, List

from .data_provider import FinancialSnapshot, YahooFinanceDataProvider
from .valuation_models import (
    AggregateValuation,
    DiscountedCashFlowModel,
    DividendDiscountModel,
    ScenarioProfile,
)


DEFAULT_SCENARIOS = [
    {"name": "Bear", "growth_rate": 0.02, "terminal_multiple": 10, "probability": 0.25},
    {"name": "Base", "growth_rate": 0.05, "terminal_multiple": 12, "probability": 0.5},
    {"name": "Bull", "growth_rate": 0.08, "terminal_multiple": 15, "probability": 0.25},
]


class ValuationService:
    def __init__(self, provider: YahooFinanceDataProvider | None = None) -> None:
        self.provider = provider or YahooFinanceDataProvider()

    def valuate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ticker = payload.get("ticker", "").strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")

        mode = payload.get("mode", "dcf").lower()
        forecast_years = int(payload.get("forecast_years", 10))
        discount_rate = float(payload.get("discount_rate", 0.1))
        margin_of_safety = float(payload.get("margin_of_safety", 0.3))
        use_owner_earnings = bool(payload.get("use_owner_earnings", False))

        scenarios_payload = payload.get("scenarios") or DEFAULT_SCENARIOS
        scenario_profiles = self._build_scenarios(scenarios_payload, forecast_years)

        snapshot = self.provider.get_snapshot(ticker)
        base_cashflow = self._select_base_cashflow(snapshot, use_owner_earnings)

        if mode == "ddm":
            base_cashflow = snapshot.dividends_per_share_ttm
            model = DividendDiscountModel(discount_rate=discount_rate, margin_of_safety=margin_of_safety)
            valuation = model.evaluate(
                base_cashflow=base_cashflow,
                current_price=snapshot.current_price,
                shares_outstanding=1.0,  # already per share
                scenarios=scenario_profiles,
            )
        else:
            model = DiscountedCashFlowModel(discount_rate=discount_rate, margin_of_safety=margin_of_safety)
            valuation = model.evaluate(
                base_cashflow=base_cashflow,
                current_price=snapshot.current_price,
                shares_outstanding=snapshot.shares_outstanding,
                scenarios=scenario_profiles,
            )

        return self._format_response(payload, snapshot, valuation, mode, use_owner_earnings)

    @staticmethod
    def _select_base_cashflow(snapshot: FinancialSnapshot, use_owner_earnings: bool) -> float:
        history = snapshot.owner_earnings_history if use_owner_earnings else snapshot.fcf_history
        if history:
            return history[0]
        fallback = snapshot.metadata.get("latest_operating_cash_flow", 0.0)
        capex = snapshot.metadata.get("latest_capex", 0.0)
        return fallback - capex

    @staticmethod
    def _build_scenarios(scenarios: List[Dict[str, Any]], years: int) -> List[ScenarioProfile]:
        profiles: List[ScenarioProfile] = []
        for item in scenarios:
            growth_input = item.get("growth_rates")
            if growth_input is None:
                growth_input = item.get("growth_rate", 0.0)
            growth_rates = _normalize_growth_series(growth_input, years)
            profiles.append(
                ScenarioProfile(
                    name=item.get("name", f"Scenario {len(profiles) + 1}"),
                    growth_rates=growth_rates,
                    terminal_multiple=float(item.get("terminal_multiple", 12.0)),
                    probability=float(item.get("probability", 1.0)),
                )
            )
        return profiles

    def _format_response(
        self,
        payload: Dict[str, Any],
        snapshot: FinancialSnapshot,
        valuation: AggregateValuation,
        mode: str,
        use_owner_earnings: bool,
    ) -> Dict[str, Any]:
        scenarios_output: List[Dict[str, Any]] = []
        for item in valuation.scenario_results:
            scenarios_output.append(
                {
                    "name": item.name,
                    "intrinsic_value": item.intrinsic_value,
                    "buy_price": item.buy_price,
                    "upside_pct": item.upside,
                    "downside_pct": item.downside,
                    "margin_of_safety_pct": item.margin_of_safety_pct,
                    "growth_rates": item.effective_growth_rates,
                    "terminal_multiple": item.terminal_multiple,
                    "cashflows": item.cashflows,
                    "discounted_cashflows": item.discounted_cashflows,
                    "terminal_value": item.terminal_value,
                    "discounted_terminal_value": item.discounted_terminal_value,
                    "warnings": item.warnings,
                }
            )

        response = {
            "ticker": snapshot.ticker,
            "mode": mode,
            "currency": snapshot.currency,
            "current_price": snapshot.current_price,
            "use_owner_earnings": use_owner_earnings,
            "shares_outstanding": snapshot.shares_outstanding,
            "weighted_intrinsic_value": valuation.weighted_intrinsic_value,
            "margin_of_safety_buy_price": valuation.margin_of_safety_buy_price,
            "scenarios": scenarios_output,
            "global_warnings": list(dict.fromkeys(snapshot.warnings + valuation.warnings)),
            "inputs": payload,
            "snapshot": {
                "fcf_history": snapshot.fcf_history,
                "owner_earnings_history": snapshot.owner_earnings_history,
                "dividends_per_share_ttm": snapshot.dividends_per_share_ttm,
                "metadata": snapshot.metadata,
            },
        }
        return response


def _normalize_growth_series(raw: Any, years: int) -> List[float]:
    if isinstance(raw, (int, float)):
        return [float(raw)] * max(years, 1)
    if isinstance(raw, list) and raw:
        cleaned: List[float] = []
        for value in raw:
            try:
                cleaned.append(float(value))
            except (TypeError, ValueError):
                cleaned.append(0.0)
        while len(cleaned) < years:
            cleaned.append(cleaned[-1])
        return cleaned[:years]
    return [0.0 for _ in range(max(years, 1))]
