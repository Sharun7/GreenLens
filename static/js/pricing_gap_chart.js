/**
 * static/js/pricing_gap_chart.js
 *
 * GreenLens — Pricing Gap Scatter Plot
 *
 * Renders a professional Chart.js scatter plot showing:
 *   • Blue dots  — fairly priced bonds
 *   • Red dots   — potentially mispriced bonds
 *   • Green line — regression model prediction (risk-adjusted fair value)
 *   • Dashed grey bands — ±2σ mispricing bounds
 *   • Hover tooltips showing issuer, gap, and PCRS details
 *
 * Usage:
 *   Include this file after Chart.js:
 *     <script src="{% static 'js/pricing_gap_chart.js' %}"></script>
 *
 *   Then call:
 *     initPricingGapChart("myCanvasId");
 *
 *   The function fetches /api/pricing/analyser/chart_data/ automatically.
 */

"use strict";

/**
 * Fetch pricing gap chart data and render the scatter plot.
 *
 * @param {string} canvasId - ID of the <canvas> element to render into
 * @param {string} [apiUrl]  - Override API URL (default: /api/pricing/analyser/chart_data/)
 * @returns {Promise<Chart>} - Resolves with the Chart.js instance
 */
async function initPricingGapChart(canvasId, apiUrl = "/api/pricing/analyser/chart_data/") {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.error(`[PricingGapChart] Canvas element #${canvasId} not found.`);
    return null;
  }

  // ── Fetch data from API ──────────────────────────────────────────────────
  let data;
  try {
    const response = await fetch(apiUrl);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
  } catch (err) {
    console.error("[PricingGapChart] Failed to fetch chart data:", err);
    _renderErrorOverlay(canvas, "Could not load pricing data. Run analyser/fit/ first.");
    return null;
  }

  const { scatter_data, regression_line, upper_band, lower_band, summary } = data;

  // ── Update summary stat badges (if present in DOM) ───────────────────────
  _updateSummaryBadges(summary);

  // ── Split scatter into fairly-priced vs mispriced ────────────────────────
  const fairPoints = scatter_data
    .filter((d) => !d.is_mispriced)
    .map((d) => ({ x: d.x, y: d.y, _meta: d }));

  const mispricedPoints = scatter_data
    .filter((d) => d.is_mispriced)
    .map((d) => ({ x: d.x, y: d.y, _meta: d }));

  // ── Chart.js configuration ────────────────────────────────────────────────
  const chartConfig = {
    type: "scatter",
    data: {
      datasets: [
        // ── Fairly priced bonds (blue) ──────────────────────────────────
        {
          label: "Fairly Priced",
          data: fairPoints,
          backgroundColor: "rgba(59, 130, 246, 0.65)",   // Tailwind blue-500
          borderColor: "rgba(37, 99, 235, 0.85)",
          borderWidth: 1,
          pointRadius: 5,
          pointHoverRadius: 8,
          order: 3,
        },
        // ── Mispriced bonds (red) ───────────────────────────────────────
        {
          label: "Potentially Mispriced",
          data: mispricedPoints,
          backgroundColor: "rgba(239, 68, 68, 0.70)",    // Tailwind red-500
          borderColor: "rgba(185, 28, 28, 0.90)",
          borderWidth: 1.5,
          pointRadius: 6,
          pointHoverRadius: 9,
          pointStyle: "triangle",
          order: 2,
        },
        // ── Regression line (green) ─────────────────────────────────────
        {
          label: "Model Fair Value",
          data: regression_line,
          type: "line",
          backgroundColor: "transparent",
          borderColor: "rgba(34, 197, 94, 1)",           // Tailwind green-500
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.3,
          order: 1,
        },
        // ── Upper 2σ band (dashed grey) ─────────────────────────────────
        {
          label: "+2σ bound",
          data: upper_band,
          type: "line",
          backgroundColor: "transparent",
          borderColor: "rgba(156, 163, 175, 0.75)",      // Tailwind gray-400
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.3,
          order: 0,
        },
        // ── Lower 2σ band (dashed grey) ─────────────────────────────────
        {
          label: "−2σ bound",
          data: lower_band,
          type: "line",
          backgroundColor: "rgba(156, 163, 175, 0.07)",
          borderColor: "rgba(156, 163, 175, 0.75)",
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.3,
          fill: "-1",   // fill between lower and upper band
          order: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      interaction: {
        mode: "nearest",
        intersect: true,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            usePointStyle: true,
            font: { size: 12 },
            filter: (item) => !item.text.includes("σ"),  // hide sigma band labels
          },
        },
        title: {
          display: true,
          text: "Physical Climate Risk Score vs Yield Spread",
          font: { size: 15, weight: "bold" },
          padding: { bottom: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const meta = ctx.raw._meta;
              if (!meta) return `(${ctx.raw.x}, ${ctx.raw.y})`;
              const gapSign = meta.gap >= 0 ? "+" : "";
              const status = meta.is_mispriced ? "⚠ MISPRICED" : "✓ Fair";
              return [
                `${status}`,
                `Issuer: ${meta.issuer}`,
                `PCRS: ${meta.x}`,
                `Actual spread: ${meta.y} bps`,
                `Fair-value spread: ${meta.predicted} bps`,
                `Gap: ${gapSign}${meta.gap} bps`,
                `Category: ${meta.category}`,
              ];
            },
          },
          backgroundColor: "rgba(15, 23, 42, 0.92)",
          titleColor: "#f8fafc",
          bodyColor: "#cbd5e1",
          borderColor: "rgba(148, 163, 184, 0.3)",
          borderWidth: 1,
          padding: 12,
          titleFont: { size: 13, weight: "bold" },
          bodyFont: { size: 12 },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: "Physical Climate Risk Score (PCRS)",
            font: { size: 13, weight: "600" },
            color: "#64748b",
          },
          min: 0,
          max: 100,
          grid: { color: "rgba(203, 213, 225, 0.4)" },
          ticks: { color: "#64748b" },
        },
        y: {
          title: {
            display: true,
            text: "Yield Spread over Benchmark (bps)",
            font: { size: 13, weight: "600" },
            color: "#64748b",
          },
          grid: { color: "rgba(203, 213, 225, 0.4)" },
          ticks: { color: "#64748b" },
        },
      },
    },
  };

  // ── Render ────────────────────────────────────────────────────────────────
  const chart = new Chart(canvas, chartConfig);

  // Expose globally for debug/console access
  window._pricingGapChart = chart;

  return chart;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _updateSummaryBadges(summary) {
  if (!summary) return;
  const mapping = {
    "pg-total": summary.n_total,
    "pg-underpriced": summary.n_underpriced,
    "pg-overpriced": summary.n_overpriced,
    "pg-fairly-priced": summary.n_fairly_priced,
    "pg-pct-underpriced": `${summary.pct_underpriced}%`,
    "pg-pct-overpriced": `${summary.pct_overpriced}%`,
    "pg-r2": summary.r2_model !== null ? summary.r2_model?.toFixed(3) : "N/A",
    "pg-gap-std": summary.gap_std_bps !== null ? `±${summary.gap_std_bps} bps` : "N/A",
  };
  for (const [id, value] of Object.entries(mapping)) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }
}

function _renderErrorOverlay(canvas, message) {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ef4444";
  ctx.font = "14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(message, canvas.width / 2, canvas.height / 2);
}
