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
const proposalLoadForm = document.querySelector("#proposal-load-form");
const proposalReview = document.querySelector("#proposal-review");
const proposalError = document.querySelector("#proposal-error");
const proposalConfirm = document.querySelector("#proposal-confirm");
const approveProposal = document.querySelector("#approve-proposal");
const rejectProposal = document.querySelector("#reject-proposal");
let loadedProposal = null;
let proposalDecisionKey = null;
let approvalInFlight = false;

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

function proposalValue(payload, key, fallback = "Not available") {
  const value = payload.simulation_payload?.[key];
  return value === undefined || value === null ? fallback : String(value);
}

function renderProposal(payload) {
  loadedProposal = payload;
  proposalDecisionKey = crypto.randomUUID();
  proposalConfirm.checked = false;
  setText("#proposal-current-assignee", payload.current_assignee_id);
  setText("#proposal-new-assignee", payload.proposed_assignee_id);
  setText("#current-employee-risk", proposalValue(payload, "current_employee_risk"));
  setText("#predicted-employee-risk", proposalValue(payload, "predicted_employee_risk"));
  setText("#current-project-risk", proposalValue(payload, "current_project_risk"));
  setText("#predicted-project-risk", proposalValue(payload, "predicted_project_risk"));
  setText("#skill-fit-comparison", proposalValue(payload, "skill_fit_comparison"));
  setText("#workload-impact", proposalValue(payload, "workload_impact"));
  setText("#dependency-impact", proposalValue(payload, "dependency_impact"));
  setText("#proposal-confidence", payload.confidence);
  setText("#proposal-expiry", new Date(payload.expires_at).toLocaleString());
  setText("#proposal-fingerprint", payload.evidence_fingerprint);
  setText(
    "#proposal-confirm-label",
    `I confirm proposal ${payload.proposal_id}: ${payload.current_assignee_id} → ${payload.proposed_assignee_id}.`,
  );
  setText("#operation-status", `${payload.state}. Jira has not been changed.`);
  proposalReview.hidden = false;
}

async function proposalRequest(path, options = {}) {
  const apiKey = sessionStorage.getItem(tabKeyName);
  if (!apiKey) {
    throw new Error("Enter the environment API key before reviewing a proposal.");
  }
  const response = await fetch(`${path}?project_key=WRD`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      Authorization: `Bearer ${apiKey}`,
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    const state = response.status === 409 ? "stale or conflicting" : "unavailable";
    throw new Error(`Proposal is ${state}. Jira has not been changed.`);
  }
  return payload;
}

async function pollProposal(proposalId, remaining = 10) {
  if (remaining <= 0) return;
  const payload = await proposalRequest(`/api/v1/proposals/${encodeURIComponent(proposalId)}`);
  renderProposal(payload);
  if (payload.state === "executing") {
    setText("#operation-status", "executing. Jira has not been changed in this phase.");
    setTimeout(() => pollProposal(proposalId, remaining - 1), 1000);
  }
}

proposalLoadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  proposalError.hidden = true;
  try {
    const proposalId = document.querySelector("#proposal-id").value;
    renderProposal(await proposalRequest(`/api/v1/proposals/${encodeURIComponent(proposalId)}`));
  } catch (error) {
    proposalError.textContent = error instanceof Error ? error.message : "Proposal unavailable.";
    proposalError.hidden = false;
  }
});

async function decideLoadedProposal(decision) {
  if (approvalInFlight || !loadedProposal) return;
  if (!proposalConfirm.checked) {
    proposalError.textContent = "Confirm the exact proposal before deciding.";
    proposalError.hidden = false;
    proposalConfirm.focus();
    return;
  }
  approvalInFlight = true;
  approveProposal.disabled = true;
  rejectProposal.disabled = true;
  proposalError.hidden = true;
  try {
    const payload = await proposalRequest(
      `/api/v1/proposals/${encodeURIComponent(loadedProposal.proposal_id)}/${decision}`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_version: loadedProposal.version,
          idempotency_key: proposalDecisionKey,
        }),
      },
    );
    renderProposal(payload);
    if (payload.state === "executing") {
      setText("#operation-status", "executing. Jira has not been changed in this phase.");
      setTimeout(() => pollProposal(payload.proposal_id), 1000);
    }
  } catch (error) {
    proposalError.textContent = error instanceof Error ? error.message : "Decision failed.";
    proposalError.hidden = false;
  } finally {
    approvalInFlight = false;
    approveProposal.disabled = false;
    rejectProposal.disabled = false;
  }
}

approveProposal.addEventListener("click", () => decideLoadedProposal("approve"));
rejectProposal.addEventListener("click", () => decideLoadedProposal("reject"));

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
