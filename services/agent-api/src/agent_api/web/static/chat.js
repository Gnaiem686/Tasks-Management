const form = document.querySelector("#risk-form");
const employeeSelect = document.querySelector("#employee-select");
const loadingState = document.querySelector("#loading-state");
const errorState = document.querySelector("#error-state");
const resultPanel = document.querySelector("#risk-result");

const labels = {
  low: "✓ Low risk",
  medium: "! Medium risk",
  high: "▲ High risk",
  critical: "◆ Critical risk",
};

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function renderFactors(factors) {
  const rows = document.querySelector("#factor-rows");
  rows.replaceChildren();
  for (const factor of factors) {
    const row = document.createElement("tr");
    const values = [
      factor.name.replaceAll("_", " "),
      factor.normalized_value.toFixed(2),
      factor.weight.toFixed(2),
      factor.contribution_points.toFixed(1),
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    rows.appendChild(row);
  }
}

function renderRisk(payload) {
  const result = payload.result;
  const insufficient = result.confidence === "insufficient-data";
  setText("#risk-score", insufficient ? "No numeric claim" : `${result.score} / 100`);
  setText("#risk-confidence", result.confidence);
  setText("#evidence-time", new Date(result.evidence_timestamp).toLocaleString());
  setText("#scoring-version", result.scoring_model_version);
  const riskLabel = document.querySelector("#risk-label");
  riskLabel.textContent = insufficient
    ? "? Insufficient data"
    : labels[result.level] || result.level;
  riskLabel.dataset.level = result.level || "insufficient-data";
  renderFactors(result.factors);

  const degraded = document.querySelector("#degraded-warning");
  degraded.hidden = !payload.degraded;
  degraded.textContent = payload.degraded
    ? `Partial result. Missing sources: ${payload.missing_sources.join(", ")}.`
    : "";

  const stale = document.querySelector("#freshness-warning");
  const ageHours = (Date.now() - Date.parse(result.evidence_timestamp)) / 3600000;
  stale.hidden = ageHours <= 24;
  stale.textContent = stale.hidden ? "" : "Stale evidence: refresh before making a decision.";
  resultPanel.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorState.hidden = true;
  resultPanel.hidden = true;
  loadingState.hidden = false;
  try {
    const employee = encodeURIComponent(employeeSelect.value);
    const response = await fetch(
      `/api/v1/employees/${employee}/overload-risk?project_key=WRD`,
      {headers: {Accept: "application/json"}},
    );
    const payload = await response.json();
    if (!response.ok) {
      const correlation = payload.correlation_id || response.headers.get("X-Correlation-ID");
      throw new Error(`${payload.message || "Analysis failed"} Reference: ${correlation || "unavailable"}`);
    }
    renderRisk(payload);
  } catch (error) {
    errorState.textContent = error instanceof Error ? error.message : "Analysis failed.";
    errorState.hidden = false;
  } finally {
    loadingState.hidden = true;
  }
});
