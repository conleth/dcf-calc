from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yfinance as yf


@dataclass
class FinancialSnapshot:
    ticker: str
    currency: str
    financial_currency: str
    shares_outstanding: float
    current_price: float
    fcf_history: List[float]
    owner_earnings_history: List[float]
    dividends_per_share_ttm: float
    metadata: Dict[str, float]
    warnings: List[str]


class YahooFinanceDataProvider:
    def __init__(self, cache_ttl: int = 1800) -> None:
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict[str, object]] = {}

    def get_snapshot(self, ticker: str) -> FinancialSnapshot:
        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("Ticker cannot be empty.")

        cached = self._cache.get(normalized)
        if cached and time.time() - cached["timestamp"] < self.cache_ttl:
            return cached["payload"]  # type: ignore[return-value]

        yf_ticker = yf.Ticker(normalized)
        cashflow = self._safe_df(yf_ticker.cashflow)
        financials = self._safe_df(yf_ticker.financials)
        balance_sheet = self._safe_df(yf_ticker.balance_sheet)

        metadata: Dict[str, float] = {}
        warnings: List[str] = []

        price = self._resolve_price(yf_ticker)
        shares_outstanding = self._resolve_shares(yf_ticker, balance_sheet)
        currency = self._resolve_currency(yf_ticker)
        financial_currency = self._resolve_financial_currency(yf_ticker)
        fx_rate = self._resolve_fx_rate(financial_currency, currency)

        fcf_history = self._scale_series(self._compute_fcf_series(cashflow), fx_rate)
        owner_earnings_history = self._scale_series(
            self._compute_owner_earnings_series(financials, cashflow), fx_rate
        )
        dividends_per_share_ttm = self._compute_dividend_ttm(yf_ticker, shares_outstanding) * fx_rate

        metadata["latest_revenue"] = self._extract_latest(financials, ["Total Revenue", "Operating Revenue"]) * fx_rate
        metadata["latest_net_income"] = self._extract_latest(
            financials,
            [
                "Net Income",
                "Net Income Common Stockholders",
                "Net Income Including Noncontrolling Interests",
            ],
        ) * fx_rate
        metadata["latest_operating_cash_flow"] = self._extract_latest(
            cashflow,
            ["Operating Cash Flow", "Total Cash From Operating Activities"],
        ) * fx_rate
        metadata["latest_capex"] = self._extract_latest(
            cashflow,
            ["Capital Expenditure", "Capital Expenditures", "Net PPE Purchase And Sale"],
        ) * fx_rate
        metadata["fx_rate"] = fx_rate
        metadata["financial_currency"] = financial_currency

        if shares_outstanding <= 0:
            warnings.append("Unable to determine shares outstanding. Intrinsic value per share may be inaccurate.")
        if not fcf_history:
            warnings.append("Missing cash flow data. DCF mode will rely on user assumptions only.")
        if dividends_per_share_ttm <= 0:
            warnings.append("No trailing dividends detected. DDM valuations may not be meaningful.")

        snapshot = FinancialSnapshot(
            ticker=normalized,
            currency=currency,
            financial_currency=financial_currency,
            shares_outstanding=shares_outstanding,
            current_price=price,
            fcf_history=fcf_history,
            owner_earnings_history=owner_earnings_history,
            dividends_per_share_ttm=dividends_per_share_ttm,
            metadata=metadata,
            warnings=warnings,
        )

        self._cache[normalized] = {"payload": snapshot, "timestamp": time.time()}
        return snapshot

    @staticmethod
    def _safe_df(df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        return df.fillna(0)

    @staticmethod
    def _resolve_price(ticker: yf.Ticker) -> float:
        fast_info = getattr(ticker, "fast_info", {}) or {}
        price = float(fast_info.get("lastPrice") or fast_info.get("last_price") or 0.0)
        if price:
            return price
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return 0.0

    @staticmethod
    def _resolve_shares(ticker: yf.Ticker, balance_sheet: pd.DataFrame) -> float:
        fast_info = getattr(ticker, "fast_info", {}) or {}
        shares = fast_info.get("sharesOutstanding") or fast_info.get("shares_outstanding")
        if shares:
            return float(shares)
        info = getattr(ticker, "info", {}) or {}
        shares = info.get("sharesOutstanding")
        if shares:
            return float(shares)
        if not balance_sheet.empty:
            key = None
            for candidate in ("Ordinary Shares Number", "Preferred Shares", "Common Stock"):  # fallback
                if candidate in balance_sheet.index:
                    key = candidate
                    break
            if key:
                return float(balance_sheet.loc[key].iloc[0])
        return 0.0

    @staticmethod
    def _resolve_currency(ticker: yf.Ticker) -> str:
        fast_info = getattr(ticker, "fast_info", {}) or {}
        currency = fast_info.get("currency")
        if currency:
            return str(currency)
        info = getattr(ticker, "info", {}) or {}
        return str(info.get("currency", "USD"))

    @staticmethod
    def _resolve_financial_currency(ticker: yf.Ticker) -> str:
        info = getattr(ticker, "info", {}) or {}
        return str(info.get("financialCurrency") or info.get("currency") or "USD")

    @staticmethod
    def _resolve_fx_rate(financial_currency: str, market_currency: str) -> float:
        financial_currency = (financial_currency or "").upper()
        market_currency = (market_currency or "").upper()
        if not financial_currency or not market_currency or financial_currency == market_currency:
            return 1.0

        pair_direct = f"{financial_currency}{market_currency}=X"
        pair_inverse = f"{market_currency}{financial_currency}=X"

        for pair, invert in ((pair_direct, False), (pair_inverse, True)):
            try:
                fx_ticker = yf.Ticker(pair)
                fast_info = getattr(fx_ticker, "fast_info", {}) or {}
                price = fast_info.get("lastPrice") or fast_info.get("last_price")
                if price and price > 0:
                    return float(1 / price) if invert else float(price)
            except Exception:
                continue
        return 1.0

    @staticmethod
    def _scale_series(series: List[float], factor: float) -> List[float]:
        if factor == 1.0 or not series:
            return series
        return [float(value) * factor for value in series]

    @staticmethod
    def _compute_fcf_series(cashflow: pd.DataFrame) -> List[float]:
        if cashflow.empty:
            return []
        free_cash_flow, found = YahooFinanceDataProvider._row_values(cashflow, ["Free Cash Flow"])
        if found and any(abs(value) > 1e-9 for value in free_cash_flow):
            return free_cash_flow

        operating, _ = YahooFinanceDataProvider._row_values(
            cashflow,
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
        )
        capex, _ = YahooFinanceDataProvider._row_values(
            cashflow,
            ["Capital Expenditure", "Capital Expenditures", "Net PPE Purchase And Sale"],
        )

        return [float(op - cap) for op, cap in zip(operating, capex)]

    @staticmethod
    def _compute_owner_earnings_series(financials: pd.DataFrame, cashflow: pd.DataFrame) -> List[float]:
        if financials.empty or cashflow.empty:
            return []
        net_income, _ = YahooFinanceDataProvider._row_values(
            financials,
            [
                "Net Income",
                "Net Income Common Stockholders",
                "Net Income Including Noncontrolling Interests",
            ],
        )
        depreciation, dep_found = YahooFinanceDataProvider._row_values(
            financials,
            [
                "Depreciation & Amortization",
                "Depreciation And Amortization",
                "Depreciation Amortization Depletion",
                "Reconciled Depreciation",
            ],
        )
        if not dep_found:
            depreciation, _ = YahooFinanceDataProvider._row_values(
                cashflow,
                [
                    "Depreciation & Amortization",
                    "Depreciation And Amortization",
                    "Depreciation Amortization Depletion",
                ],
            )

        capex, _ = YahooFinanceDataProvider._row_values(
            cashflow,
            ["Capital Expenditure", "Capital Expenditures", "Net PPE Purchase And Sale"],
        )
        owner: List[float] = []
        for ni, dep, cap in zip(net_income, depreciation, capex):
            owner.append(float(ni + dep - cap))
        return owner

    @staticmethod
    def _compute_dividend_ttm(ticker: yf.Ticker, shares_outstanding: float) -> float:
        dividends = getattr(ticker, "dividends", None)
        if dividends is None or dividends.empty:
            return 0.0
        trailing = dividends[dividends.index >= (dividends.index.max() - pd.DateOffset(years=1))]
        total = float(trailing.sum())
        if shares_outstanding > 0:
            return total * 1.0  # dividends are already per share
        return total

    @staticmethod
    def _extract_latest(df: pd.DataFrame, row_labels: Iterable[str]) -> float:
        if df.empty:
            return 0.0
        if isinstance(row_labels, str):
            row_labels = [row_labels]
        for label in row_labels:
            if label in df.index:
                return float(df.loc[label].fillna(0).iloc[0])
        return 0.0

    @staticmethod
    def _row_values(df: pd.DataFrame, row_labels: Iterable[str]) -> Tuple[List[float], bool]:
        if isinstance(row_labels, str):
            row_labels = [row_labels]
        if df.empty:
            return ([], False)
        for label in row_labels:
            if label in df.index:
                series = df.loc[label].fillna(0)
                return ([float(x) for x in series.tolist()], True)
        return ([0.0 for _ in df.columns], False)
