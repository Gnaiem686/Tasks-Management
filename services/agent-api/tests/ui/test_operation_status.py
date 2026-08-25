import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


def _run_chat_failure_runtime(mode: str) -> dict[str, object]:
    chat_js_path = WEB / "static" / "chat.js"
    node_script = f"""
;(async () => {{
const fs = require("fs");
const vm = require("vm");

const mode = {json.dumps(mode)};

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
    this.parentNode = null;
    this._text = "";
  }}

  set textContent(value) {{
    this._text = value == null ? "" : String(value);
    this.children = [];
  }}

  get textContent() {{
    return this._text + this.children.map((child) => child.textContent).join("");
  }}

  get lastElementChild() {{
    return this.children[this.children.length - 1] || null;
  }}

  append(...items) {{
    for (const item of items) {{
      if (item === undefined || item === null) continue;
      if (typeof item === "string") {{
        const textNode = new Element("#text");
        textNode.textContent = item;
        textNode.parentNode = this;
        this.children.push(textNode);
      }} else {{
        item.parentNode = this;
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

  showModal() {{
    this.open = true;
  }}

  close() {{
    this.open = false;
  }}

  remove() {{
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(
      (child) => child !== this
    );
    this.parentNode = null;
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

const document = {{
  querySelector(selector) {{
    if (selector.startsWith("#")) return elements[selector.slice(1)] || null;
    throw new Error(`Unsupported selector: ${{selector}}`);
  }},
  querySelectorAll(selector) {{
    if (selector === "[data-question]") return [];
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
    return {{
      ok: true,
      status: 200,
      headers: {{ get() {{ return null; }} }},
      json: async () => ({{ items: [{{ key: "WFD", name: "Workforce Real Data" }}] }}),
    }};
  }}
  if (String(path).startsWith("/api/v1/dashboard?")) {{
    return {{
      ok: true,
      status: 200,
      headers: {{ get() {{ return "corr-ui-dashboard"; }} }},
      json: async () => ({{
        schema_version: "1.0",
        correlation_id: "corr-ui-dashboard",
        evidence_timestamp: "2026-08-20T12:00:00+00:00",
        project: {{
          key: "WFD",
          name: "Workforce Real Data",
          total_tasks: 5,
          completed_tasks: 2,
          active_tasks: 3,
          overdue_tasks: 1,
          due_soon_tasks: 1,
          blocked_tasks: 1,
          missing_estimate_tasks: 0,
          completion_percent: 40,
        }},
        employees: [],
        tasks: [],
        alerts: [],
        workload: {{ overloaded: 0, balanced: 3, insufficient_data: 0 }},
        degraded: false,
        missing_sources: [],
        missing_evidence: [],
      }}),
    }};
  }}
  if (String(path).startsWith("/api/v1/investigations?")) {{
    if (mode === "fetch-reject") {{
      throw new TypeError("Failed to fetch");
    }}
    return {{
      ok: false,
      status: 503,
      headers: {{
        get(name) {{
          return name.toLowerCase() === "x-correlation-id" ? "corr-ui-503" : null;
        }},
      }},
      json: async () => {{
        if (mode === "invalid-json") {{
          throw new SyntaxError("Unexpected token < in JSON at position 0");
        }}
        if (mode === "empty-json") {{
          throw new SyntaxError("Unexpected end of JSON input");
        }}
        return {{
          detail: {{
            error_code: "INVESTIGATION_UNAVAILABLE",
            correlation_id: "corr-ui-503",
          }},
        }};
      }},
    }};
  }}
  throw new Error(`Unexpected fetch path: ${{path}}`);
}};

const script = fs.readFileSync({json.dumps(str(chat_js_path))}, "utf8");
vm.runInThisContext(script, {{ filename: "chat.js" }});
await new Promise((resolve) => setImmediate(resolve));
await new Promise((resolve) => setImmediate(resolve));
await sendChat("Which task is riskiest right now?");
await new Promise((resolve) => setImmediate(resolve));
await new Promise((resolve) => setImmediate(resolve));

console.log(JSON.stringify({{
  messages: elements["chat-messages"].children.map((node) => ({{
    text: node.textContent,
    className: node.className,
  }})),
}}));
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
    return cast(dict[str, object], json.loads(completed.stdout))


@pytest.mark.ui
def test_public_dashboard_only_posts_chat_reads() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    assert 'method:"POST"' in script
    assert "/api/v1/investigations" in script
    assert "/api/v1/proposals" not in script


@pytest.mark.ui
def test_chat_replaces_raw_503_status_with_friendly_availability_copy() -> None:
    result = _run_chat_failure_runtime("http-503")
    messages = cast(list[dict[str, str]], result["messages"])

    assert messages[-1]["className"] == "error-message"
    assert "Request failed (503)" not in messages[-1]["text"]
    assert "corr-ui-503" in messages[-1]["text"]


@pytest.mark.ui
def test_chat_hides_raw_fetch_rejection_text() -> None:
    result = _run_chat_failure_runtime("fetch-reject")
    messages = cast(list[dict[str, str]], result["messages"])

    assert messages[-1]["className"] == "error-message"
    assert "Failed to fetch" not in messages[-1]["text"]
    assert messages[-1]["text"] == (
        "The AI assistant is temporarily unavailable right now. "
        "Please try again in a moment."
    )


@pytest.mark.ui
@pytest.mark.parametrize(
    ("mode", "forbidden"),
    [
        ("invalid-json", "Unexpected token < in JSON at position 0"),
        ("empty-json", "Unexpected end of JSON input"),
    ],
)
def test_chat_hides_raw_json_parse_errors_and_keeps_correlation(
    mode: str, forbidden: str
) -> None:
    result = _run_chat_failure_runtime(mode)
    messages = cast(list[dict[str, str]], result["messages"])

    assert messages[-1]["className"] == "error-message"
    assert forbidden not in messages[-1]["text"]
    assert "corr-ui-503" in messages[-1]["text"]
