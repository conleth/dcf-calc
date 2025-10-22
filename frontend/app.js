const scenarioDefaults = [
  { id: "bear", name: "Bear", growth: 3, terminal: 10, probability: 25 },
  { id: "base", name: "Base", growth: 6, terminal: 12, probability: 50 },
  { id: "bull", name: "Bull", growth: 9, terminal: 15, probability: 25 }
];

const scenariosContainer = document.getElementById("scenarios-container");
const form = document.getElementById("valuation-form");
const modeSelect = document.getElementById("mode");
const ownerToggle = document.getElementById("use_owner_earnings");
const warningsCard = document.getElementById("warnings");
const warningsList = document.getElementById("warnings-list");
const resultsCard = document.getElementById("results");
const intrinsicLabel = document.getElementById("intrinsic-value");
const buyLabel = document.getElementById("buy-price");
const marketLabel = document.getElementById("market-price");
const upsideLabel = document.getElementById("upside");
const scenarioTableContainer = document.getElementById("scenario-table");
const batchPanel = document.getElementById("batch-panel");
const batchTrigger = document.getElementById("batch-trigger");
const batchClose = document.getElementById("close-batch");
const batchRun = document.getElementById("run-batch");
const batchTickers = document.getElementById("batch-tickers");
const batchResults = document.getElementById("batch-results");

const currencyFormatter = (currency) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD" });
const percentFormatter = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1 });

let scenarioChart;
let cashflowChart;

renderScenarioCards();
modeSelect.addEventListener("change", handleModeChange);
form.addEventListener("submit", handleSubmit);
batchTrigger.addEventListener("click", () => toggleBatch(true));
batchClose.addEventListener("click", () => toggleBatch(false));
batchRun.addEventListener("click", runBatch);
handleModeChange();

function renderScenarioCards() {
  scenariosContainer.innerHTML = scenarioDefaults
    .map(
      (scenario) => `
        <div class="scenario-card" data-scenario="${scenario.id}">
            <h4>${scenario.name}</h4>
            <label>
                <div class="mini-label">Single Growth Rate (%)</div>
                <input type="number" step="0.1" value="${scenario.growth}" class="growth-rate">
            </label>
            <label>
                <div class="mini-label">Year-by-Year Growth (% comma separated)</div>
                <textarea class="growth-series" placeholder="e.g. 8,7,6"></textarea>
            </label>
            <label>
                <div class="mini-label">Terminal Multiple</div>
                <input type="number" step="0.1" value="${scenario.terminal}" class="terminal-multiple">
            </label>
            <label>
                <div class="mini-label">Probability Weight (%)</div>
                <input type="number" step="1" value="${scenario.probability}" class="probability">
            </label>
        </div>
      `
    )
    .join("");
}

function handleModeChange() {
  const disableOwner = modeSelect.value === "ddm";
  ownerToggle.checked = ownerToggle.checked && !disableOwner;
  ownerToggle.disabled = disableOwner;
}

async function handleSubmit(event) {
  event.preventDefault();
  const payload = buildPayload(true);
  if (!payload) {
    return;
  }
  await runValuation(payload);
}

function buildPayload(includeTicker) {
  const ticker = document.getElementById("ticker").value.trim();
  if (includeTicker && !ticker) {
    alert("Please provide a ticker symbol.");
    return null;
  }
  const forecastYears = clampNumber(parseInt(document.getElementById("forecast_years").value, 10) || 10, 1, 30);
  const discountRate = parseFloat(document.getElementById("discount_rate").value) || 0;
  const marginSafety = parseFloat(document.getElementById("margin_of_safety").value) || 0;

  const scenarios = Array.from(document.querySelectorAll(".scenario-card")).map((el) => {
    const growthInput = el.querySelector(".growth-rate").value;
    const growthSeriesRaw = el.querySelector(".growth-series").value;
    const terminal = parseFloat(el.querySelector(".terminal-multiple").value) || 0;
    const probability = parseFloat(el.querySelector(".probability").value) || 0;
    const growthRates = buildGrowthSeries(growthInput, growthSeriesRaw, forecastYears);
    return {
      name: el.querySelector("h4").textContent || "Scenario",
      growth_rates: growthRates,
      terminal_multiple: terminal,
      probability: probability / 100,
    };
  });

  const payload = {
    mode: modeSelect.value,
    forecast_years: forecastYears,
    discount_rate: (discountRate || 0) / 100,
    margin_of_safety: (marginSafety || 0) / 100,
    scenarios,
    use_owner_earnings: ownerToggle.checked,
  };

  if (includeTicker) {
    payload.ticker = ticker;
  }
  return payload;
}

function buildGrowthSeries(singleRate, seriesText, years) {
  const growths = [];
  if (seriesText.trim()) {
    seriesText
      .split(/[,\n]/)
      .map((chunk) => chunk.trim())
      .filter((chunk) => chunk)
      .forEach((chunk) => {
        const value = parseFloat(chunk);
        if (!Number.isNaN(value)) {
          growths.push(normalizeRate(value));
        }
      });
  }
  if (!growths.length) {
    const fallback = parseFloat(singleRate);
    const rate = Number.isNaN(fallback) ? 0 : normalizeRate(fallback);
    return Array(years).fill(rate);
  }
  if (growths.length < years) {
    const padding = growths[growths.length - 1];
    while (growths.length < years) {
      growths.push(padding);
    }
  }
  return growths.slice(0, years);
}

function normalizeRate(value) {
  return value > 1 ? value / 100 : value;
}

function clampNumber(value, min, max) {
  if (Number.isNaN(value)) return min;
  return Math.min(Math.max(value, min), max);
}

async function runValuation(payload) {
  setLoading(true);
  try {
    const response = await fetch("/api/valuation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to complete valuation.");
    }
    renderResults(data);
  } catch (error) {
    alert(error.message);
  } finally {
    setLoading(false);
  }
}

function renderResults(data) {
  const formatter = currencyFormatter(data.currency);
  const intrinsic = data.weighted_intrinsic_value;
  const buyPrice = data.margin_of_safety_buy_price;
  const current = data.current_price;

  intrinsicLabel.textContent = formatter.format(intrinsic);
  buyLabel.textContent = formatter.format(buyPrice);
  marketLabel.textContent = current ? formatter.format(current) : "N/A";

  const upside = current ? (intrinsic / current - 1) : 0;
  const downside = current ? (buyPrice / current - 1) : 0;
  const upsideText = `${percentFormatter.format(upside)} upside`;
  const downsideText = `${percentFormatter.format(downside)} buy target`;
  upsideLabel.textContent = `${upsideText} | ${downsideText}`;

  const allWarnings = [...(data.global_warnings || [])];
  const scenarioWarnings = (data.scenarios || []).flatMap((scenario) => scenario.warnings || []);
  const combinedWarnings = [...allWarnings, ...scenarioWarnings];
  renderWarnings(combinedWarnings);
  renderScenarioTable(data, formatter);
  renderCharts(data, formatter);

  resultsCard.hidden = false;
}

function renderWarnings(warnings) {
  warningsList.innerHTML = "";
  if (!warnings.length) {
    warningsCard.hidden = true;
    return;
  }
  const unique = [...new Set(warnings)];
  unique.forEach((warning) => {
    const li = document.createElement("li");
    li.textContent = warning;
    warningsList.appendChild(li);
  });
  warningsCard.hidden = false;
}

function renderScenarioTable(data, formatter) {
  const scenarios = data.scenarios || [];
  if (!scenarios.length) {
    scenarioTableContainer.innerHTML = "";
    return;
  }
  const rows = scenarios
    .map((scenario) => {
      const growthString = scenario.growth_rates.map((g) => percentFormatter.format(g)).join(", ");
      return `
        <tr>
          <td>${scenario.name}</td>
          <td>${formatter.format(scenario.intrinsic_value)}</td>
          <td>${formatter.format(scenario.buy_price)}</td>
          <td>${percentFormatter.format(scenario.upside_pct)}</td>
          <td>${percentFormatter.format(scenario.downside_pct)}</td>
          <td>${scenario.terminal_multiple.toFixed(1)}x</td>
          <td>${growthString}</td>
        </tr>
      `;
    })
    .join("");

  scenarioTableContainer.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Intrinsic Value</th>
          <th>Buy Price</th>
          <th>Upside</th>
          <th>Buy Target</th>
          <th>Terminal Multiple</th>
          <th>Growth Path</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderCharts(data, formatter) {
  const scenarios = data.scenarios || [];
  const labels = scenarios.map((s) => s.name);
  const intrinsic = scenarios.map((s) => s.intrinsic_value);
  const buyPrices = scenarios.map((s) => s.buy_price);
  const current = data.current_price;
  const currentSeries = scenarios.map(() => current);

  const scenarioCtx = document.getElementById("scenarioChart").getContext("2d");
  if (scenarioChart) scenarioChart.destroy();
  scenarioChart = new Chart(scenarioCtx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Intrinsic Value",
          data: intrinsic,
          backgroundColor: "rgba(56, 189, 248, 0.7)",
        },
        {
          label: "Buy Price",
          data: buyPrices,
          backgroundColor: "rgba(34, 197, 94, 0.6)",
        },
        {
          label: "Current Price",
          data: currentSeries,
          backgroundColor: "rgba(248, 113, 113, 0.6)",
        },
      ],
    },
    options: {
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${formatter.format(ctx.parsed.y)}`,
          },
        },
      },
      responsive: true,
      scales: {
        y: {
          ticks: {
            callback: (value) => formatter.format(value),
          },
        },
      },
    },
  });

  const focusScenario = scenarios.find((s) => s.name.toLowerCase() === "base") || scenarios[0];
  const cashflowCtx = document.getElementById("cashflowChart").getContext("2d");
  if (cashflowChart) cashflowChart.destroy();
  if (focusScenario) {
    const years = focusScenario.cashflows.map((_, idx) => `Year ${idx + 1}`);
    cashflowChart = new Chart(cashflowCtx, {
      type: "line",
      data: {
        labels: years,
        datasets: [
          {
            label: "Projected Cashflows",
            data: focusScenario.cashflows,
            borderColor: "rgba(56, 189, 248, 0.8)",
            backgroundColor: "rgba(56, 189, 248, 0.25)",
            tension: 0.25,
          },
          {
            label: "Discounted Cashflows",
            data: focusScenario.discounted_cashflows,
            borderColor: "rgba(34, 197, 94, 0.8)",
            backgroundColor: "rgba(34, 197, 94, 0.25)",
            tension: 0.25,
          },
        ],
      },
      options: {
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${formatter.format(ctx.parsed.y)}`,
            },
          },
        },
        responsive: true,
        scales: {
          y: {
            ticks: {
              callback: (value) => formatter.format(value),
            },
          },
        },
      },
    });
  }
}

function setLoading(isLoading) {
  form.querySelectorAll("button, input, select, textarea").forEach((el) => {
    el.disabled = isLoading;
  });
  if (!isLoading) {
    handleModeChange();
  }
}

function toggleBatch(show) {
  batchPanel.hidden = !show;
  if (!show) {
    batchResults.innerHTML = "";
  }
}

async function runBatch() {
  const payload = buildPayload(false);
  if (!payload) return;
  const tickers = batchTickers.value
    .split(/\n/)
    .map((line) => line.trim().toUpperCase())
    .filter((ticker) => ticker);
  if (!tickers.length) {
    alert("Enter at least one ticker for batch mode.");
    return;
  }
  setLoading(true);
  try {
    const response = await fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, tickers }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to run batch valuations.");
    }
    renderBatchResults(data.results || []);
  } catch (error) {
    alert(error.message);
  } finally {
    setLoading(false);
  }
}

function renderBatchResults(results) {
  batchResults.innerHTML = "";
  const rows = results.map(({ ticker, result }) => {
    const formatter = currencyFormatter(result.currency);
    const intrinsic = formatter.format(result.weighted_intrinsic_value);
    const buy = formatter.format(result.margin_of_safety_buy_price);
    const current = result.current_price ? formatter.format(result.current_price) : "N/A";
    const upsideValue = result.current_price
      ? result.weighted_intrinsic_value / result.current_price - 1
      : null;
    const upside = upsideValue !== null ? percentFormatter.format(upsideValue) : "–";
    const upsideClass = upsideValue !== null && upsideValue < 0 ? "negative" : "";
    return `
      <div class="batch-row">
        <div><strong>${ticker}</strong></div>
        <div>Intrinsic: ${intrinsic}</div>
        <div>Buy @: ${buy}</div>
        <div>Market: ${current}</div>
        <div class="${upsideClass}">Upside: ${upside}</div>
      </div>
    `;
  });
  batchResults.innerHTML = rows.join("");
}
