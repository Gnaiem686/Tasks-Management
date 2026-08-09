const form = document.querySelector("#risk-form");
const employeeSelect = document.querySelector("#employee-select");
const loadingState = document.querySelector("#loading-state");
const errorState = document.querySelector("#error-state");
const resultPanel = document.querySelector("#risk-result");
const accessForm = document.querySelector("#access-form");
const apiKeyInput = document.querySelector("#api-key");
const accessStatus = document.querySelector("#access-status");
const chatForm = document.querySelector("#chat-form");
const chatLoading = document.querySelector("#chat-loading");
const chatError = document.querySelector("#chat-error");
const chatAnswer = document.querySelector("#chat-answer");
const tabKeyName = "workforceManagerApiKey";

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

function renderList(selector, values) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  for (const value of values) {
    const item = document.createElement("li");
    item.appendChild(document.createTextNode(value));
    list.appendChild(item);
  }
}

function renderAnswer(payload) {
  const explanation = payload.explanation;
  const guidance = payload.capability_guidance;
  setText("#answer-summary", explanation ? explanation.summary : guidance);
  renderList("#answer-causes", explanation ? explanation.root_causes : []);
  renderList(
    "#answer-recommendations",
    explanation
      ? explanation.recommendations.map((item) => `${item.action}: ${item.reason}`)
      : [],
  );
  renderList("#chat-citations", explanation ? explanation.citations : []);
  setText("#chat-correlation", payload.correlation_id || "unavailable");
  chatAnswer.hidden = false;
}

accessForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sessionStorage.setItem(tabKeyName, apiKeyInput.value);
  apiKeyInput.value = "";
  accessStatus.textContent = "API key ready for this tab.";
});

document.querySelector("#clear-key").addEventListener("click", () => {
  sessionStorage.removeItem(tabKeyName);
  apiKeyInput.value = "";
  accessStatus.textContent = "API key cleared.";
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiKey = sessionStorage.getItem(tabKeyName);
  chatError.hidden = true;
  chatAnswer.hidden = true;
  if (!apiKey) {
    chatError.textContent = "Enter the environment API key before asking.";
    chatError.hidden = false;
    return;
  }
  chatLoading.hidden = false;
  try {
    const response = await fetch("/api/v1/investigations?project_key=WRD", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        question: document.querySelector("#manager-question").value,
        context: {
          employee_id: employeeSelect.value,
          project_key: "WRD",
        },
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const correlation = response.headers.get("X-Correlation-ID");
      throw new Error(`Investigation failed. Reference: ${correlation || "unavailable"}`);
    }
    renderAnswer(payload);
  } catch (error) {
    chatError.textContent = error instanceof Error ? error.message : "Investigation failed.";
    chatError.hidden = false;
  } finally {
    chatLoading.hidden = true;
  }
});

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
