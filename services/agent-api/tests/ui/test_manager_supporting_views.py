from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


def _snapshot(
    *,
    employee_count: int,
    alert_count: int,
    task_count: int,
) -> dict[str, object]:
    employees = [
        {
            "employee_id": f"EMP-{index:03d}",
            "display_name": f"Employee {index}",
            "role": "Engineer",
            "skills": ["Python"],
            "capacity_hours": 40,
            "remaining_hours": 18 + index,
            "active_tasks": 2 + index,
            "score": 35 + index,
            "level": "high" if index % 3 == 0 else "medium" if index % 2 == 0 else "low",
            "top_risk": f"Risk {index}",
        }
        for index in range(1, employee_count + 1)
    ]
    alerts = [
        {
            "subject_id": f"WFD-{index}",
            "severity": "critical" if index == 1 else "high" if index % 2 else "medium",
            "reason": f"Alert reason {index}",
        }
        for index in range(1, alert_count + 1)
    ]
    tasks = [
        {
            "key": f"WFD-{index}",
            "summary": f"Task {index}",
            "status": "Blocked" if index % 2 else "In Progress",
            "priority": "High",
            "assignee_id": f"EMP-{index:03d}",
            "assignee_name": f"Employee {index}",
            "due_date": f"2026-08-{20 + index:02d}",
            "original_hours": 16,
            "remaining_hours": 4 + index,
            "required_skills": ["Python"],
            "blocker": None,
            "dependencies": [],
            "jira_url": f"https://example.atlassian.net/browse/WFD-{index}",
        }
        for index in range(1, task_count + 1)
    ]
    return {
        "schema_version": "1.0",
        "correlation_id": "corr-ui-runtime",
        "evidence_timestamp": "2026-08-20T12:00:00+00:00",
        "project": {
            "key": "WFD",
            "name": "Workforce Real Data",
            "total_tasks": 22,
            "completed_tasks": 8,
            "active_tasks": 14,
            "overdue_tasks": 3,
            "due_soon_tasks": 5,
            "blocked_tasks": 2,
            "missing_estimate_tasks": 1,
            "completion_percent": 36,
        },
        "employees": employees,
        "tasks": tasks,
        "alerts": alerts,
        "workload": {
            "overloaded": 2,
            "balanced": max(employee_count - 3, 0),
            "insufficient_data": 1,
        },
        "degraded": False,
        "missing_sources": [],
        "missing_evidence": [],
    }


def _run_dashboard_runtime(snapshot: dict[str, object]) -> dict[str, object]:
    chat_js_path = WEB / "static" / "chat.js"
    node_script = f"""
;(async () => {{
const fs = require("fs");
const vm = require("vm");

const snapshot = {json.dumps(snapshot)};

class Element {{
  constructor(tagName, id = null) {{
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.className = "";
    this.children = [];
    this.attributes = {{}};
    this.dataset = {{}};
    this.listeners = {{}};
    this.style = {{}};
    this.disabled = false;
    this.value = "";
    this.tabIndex = 0;
    this.open = false;
    this._text = "";
  }}

  set textContent(value) {{
    this._text = value == null ? "" : String(value);
    this.children = [];
  }}

  get textContent() {{
    return this._text + this.children.map((child) => child.textContent).join("");
  }}

  append(...items) {{
    for (const item of items) {{
      if (item === undefined || item === null) continue;
      if (typeof item === "string") {{
        const textNode = new Element("#text");
        textNode.textContent = item;
        this.children.push(textNode);
      }} else {{
        this.children.push(item);
      }}
    }}
  }}

  replaceChildren(...items) {{
    this.children = [];
    this._text = "";
    this.append(...items);
  }}

  addEventListener(type, listener) {{
    this.listeners[type] = listener;
  }}

  setAttribute(name, value) {{
    this.attributes[name] = String(value);
  }}

  getAttribute(name) {{
    return this.attributes[name];
  }}

  showModal() {{
    this.open = true;
  }}

  close() {{
    this.open = false;
  }}

  remove() {{
    this.removed = true;
  }}

  scrollIntoView() {{}}
}}

const ids = [
  "project-select",
  "refresh-dashboard",
  "summary-cards",
  "employee-rows",
  "risk-alerts",
  "alert-list",
  "project-progress",
  "progress-content",
  "workload-distribution",
  "workload-content",
  "task-rows",
  "detail-drawer",
  "detail-title",
  "detail-content",
  "chat-panel",
  "chat-messages",
  "chat-composer",
  "manager-question",
  "page-status",
  "evidence-time",
  "view-all-employees",
  "view-all-alerts",
  "view-all-tasks",
  "close-detail",
  "clear-chat",
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element("div", id)]));
elements["project-select"].tagName = "SELECT";
elements["refresh-dashboard"].tagName = "BUTTON";
elements["chat-composer"].tagName = "FORM";
elements["manager-question"].tagName = "TEXTAREA";
elements["detail-drawer"].tagName = "DIALOG";
elements["detail-title"].tagName = "H2";
elements["view-all-employees"].tagName = "BUTTON";
elements["view-all-alerts"].tagName = "BUTTON";
elements["view-all-tasks"].tagName = "BUTTON";
elements["close-detail"].tagName = "BUTTON";
elements["clear-chat"].tagName = "BUTTON";

const questionButtons = [
  "Which employees are at risk and why?",
  "Which tasks are most likely to miss their deadlines?",
  "Which work is blocked right now?",
].map((question, index) => {{
  const button = new Element("button", `suggestion-${{index}}`);
  button.dataset.question = question;
  return button;
}});

const document = {{
  querySelector(selector) {{
    if (selector.startsWith("#")) return elements[selector.slice(1)] || null;
    throw new Error(`Unsupported selector: ${{selector}}`);
  }},
  querySelectorAll(selector) {{
    if (selector === "[data-question]") return questionButtons;
    return [];
  }},
  createElement(tag) {{
    return new Element(tag);
  }},
}};

const sessionStorageState = new Map();
global.document = document;
global.window = global;
global.sessionStorage = {{
  getItem(key) {{
    return sessionStorageState.has(key) ? sessionStorageState.get(key) : null;
  }},
  setItem(key, value) {{
    sessionStorageState.set(key, String(value));
  }},
  removeItem(key) {{
    sessionStorageState.delete(key);
  }},
}};
global.history = {{ replaceState() {{}} }};
global.location = {{ search: "" }};
global.fetch = async (path) => {{
  if (path === "/api/v1/projects") {{
    return {{ ok: true, json: async () => ({{ items: [{{ key: "WFD", name: "Workforce Real Data" }}] }}) }};
  }}
  if (String(path).startsWith("/api/v1/dashboard?")) {{
    return {{ ok: true, json: async () => snapshot }};
  }}
  throw new Error(`Unexpected fetch path: ${{path}}`);
}};

const script = fs.readFileSync({json.dumps(str(chat_js_path))}, "utf8");
vm.runInThisContext(script, {{ filename: "chat.js" }});
await new Promise((resolve) => setImmediate(resolve));
await new Promise((resolve) => setImmediate(resolve));

const result = {{
  summary_cards: elements["summary-cards"].children.length,
  employee_rows: elements["employee-rows"].children.length,
  alert_items: elements["alert-list"].children.length,
  task_rows: elements["task-rows"].children.length,
  employee_view_all_disabled: elements["view-all-employees"].disabled,
  alert_view_all_disabled: elements["view-all-alerts"].disabled,
  task_view_all_disabled: elements["view-all-tasks"].disabled,
  page_status: elements["page-status"].textContent,
}};

elements["view-all-employees"].onclick();
result.employee_drawer_title = elements["detail-title"].textContent;
result.employee_drawer_sections = elements["detail-content"].children.length;
result.employee_drawer_first = elements["detail-content"].children[0].textContent;

elements["view-all-alerts"].onclick();
result.alert_drawer_title = elements["detail-title"].textContent;
result.alert_drawer_sections = elements["detail-content"].children.length;
result.alert_drawer_first = elements["detail-content"].children[0].textContent;

elements["view-all-tasks"].onclick();
result.task_drawer_title = elements["detail-title"].textContent;
result.task_drawer_sections = elements["detail-content"].children.length;
result.task_drawer_first = elements["detail-content"].children[0].textContent;

console.log(JSON.stringify(result));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""
    completed = subprocess.run(
        ["node", "-"],
        input=node_script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.ui
def test_dashboard_runtime_renders_bounded_previews_and_populates_drawers() -> None:
    result = _run_dashboard_runtime(
        _snapshot(employee_count=6, alert_count=5, task_count=6)
    )

    assert result["summary_cards"] == 4
    assert result["employee_rows"] == 5
    assert result["alert_items"] == 4
    assert result["task_rows"] == 5
    assert result["employee_view_all_disabled"] is False
    assert result["alert_view_all_disabled"] is False
    assert result["task_view_all_disabled"] is False
    assert result["employee_drawer_title"] == "All employees"
    assert result["employee_drawer_sections"] == 6
    assert "Employee 1" in result["employee_drawer_first"]
    assert result["alert_drawer_title"] == "All alerts"
    assert result["alert_drawer_sections"] == 5
    assert "WFD-1" in result["alert_drawer_first"]
    assert result["task_drawer_title"] == "All tasks"
    assert result["task_drawer_sections"] == 6
    assert "WFD-1 · Task 1" in result["task_drawer_first"]
    assert "Current project evidence loaded." in result["page_status"]


@pytest.mark.ui
def test_view_all_buttons_disable_when_collections_fit_preview_limits() -> None:
    result = _run_dashboard_runtime(
        _snapshot(employee_count=5, alert_count=4, task_count=5)
    )

    assert result["employee_rows"] == 5
    assert result["alert_items"] == 4
    assert result["task_rows"] == 5
    assert result["employee_view_all_disabled"] is True
    assert result["alert_view_all_disabled"] is True
    assert result["task_view_all_disabled"] is True


@pytest.mark.ui
def test_tables_and_status_are_accessible() -> None:
    html = (WEB / "templates" / "chat.html").read_text()
    styles = (WEB / "static" / "styles.css").read_text()
    assert html.count("<caption>") >= 2
    assert 'aria-live="polite"' in html
    assert ":focus-visible" in styles
    assert ".risk-state-good{" in styles
    assert ".risk-state-warning{" in styles
    assert ".risk-state-critical{" in styles
