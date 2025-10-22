# Intrinsic Value Workbench

A local-first discounted cash flow (DCF) and dividend discount model (DDM) workbench inspired by Warren Buffett and Sven Carlin. Pulls fundamentals from Yahoo Finance via `yfinance`, lets you stress test bear/base/bull scenarios, and visualises intrinsic value vs. market price with built-in margin of safety guidance.

## Features

- Dual valuation engines
  - **DCF** using trailing free cash flow or owner earnings
  - **DDM** for dividend-focused analysis
- Scenario modelling with configurable growth paths, terminal multiples, and probability weights
- Automatic guardrails that flag aggressive growth rates and terminal multiples
- Margin of safety overlay with conservative buy targets
- Batch mode for valuing multiple tickers with shared assumptions
- Lightweight responsive UI powered by Chart.js

## Quick Start

1. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the app:**
   ```bash
   python app.py
   ```
4. **Open the UI:** visit [http://localhost:5000](http://localhost:5000) in your browser.

## Using the Workbench

1. Enter a ticker and choose **DCF** or **DDM** mode. DCF supports toggling to owner earnings (Net Income + Depreciation − CapEx).
2. Set forecast horizon, discount rate (10–15% suggested), and desired margin of safety (common choice: 30%).
3. Configure Bear/Base/Bull scenarios:
   - Either supply a single growth rate or detailed per-year percentages (comma separated).
   - Keep growth ≤ 15% and terminal multiple ≤ 20× to stay conservative; warnings appear when inputs look heroic.
   - Adjust probability weights to influence the blended intrinsic value.
4. Run the valuation to see intrinsic value, buy price, and upside/downside alongside scenario-level detail and charts.
5. Use **Batch Mode** to analyse multiple tickers at once with the same assumptions. Results appear in a quick-scan table.

## Notes & Guidance

- Data quality depends on Yahoo Finance. Cross-check figures (especially cash flow items) before making decisions.
- Dividends are sourced from the trailing 12 months. Zero dividends disable DDM valuations.
- Owner earnings require reliable depreciation and CapEx data; if unavailable the tool falls back to operating cash flow minus CapEx.
- Network access is required for `yfinance` to fetch data on first request; results are cached briefly to keep the UI responsive.
- Charts highlight the Base scenario cash-flow projections. Adjust assumptions iteratively and watch how the buy targets shift.

## Next Ideas

- Add alternative data providers (Alpha Vantage, FMP) by swapping `YahooFinanceDataProvider` in `backend/valuation_service.py`.
- Extend scenario inputs with separate near-term/long-term growth stages.
- Export valuations to CSV or PDF for record keeping.

Value investing stays patient and disciplined—treat optimistic inputs with skepticism and insist on a comfortable margin of safety.
