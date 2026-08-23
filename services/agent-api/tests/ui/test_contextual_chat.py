import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from agent_api.main import app
from httpx import ASGITransport, AsyncClient

WEB = Path(__file__).parents[2] / "src" / "agent_api" / "web"


def _run_chat_runtime(
    *,
    investigation_status: int = 200,
    investigation_payload: dict[str, object] | None = None,
    investigation_headers: dict[str, str] | None = None,
    investigation_responses: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    chat_js_path = WEB / "static" / "chat.js"
    node_script = f"""
;(async () => {{
const fs = require("fs");
const vm = require("vm");

const investigationStatus = {json.dumps(investigation_status)};
const investigationPayload = {json.dumps(investigation_payload)};
const investigationHeaders = {json.dumps(investigation_headers or {})};
const investigationResponses = {json.dumps(investigation_responses)};
let investigationCallCount = 0;

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
  "cancel-chat",
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
elements["cancel-chat"].tagName = "BUTTON";

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
global.window.addEventListener = () => {{}};
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
global.setTimeout = (callback) => {{ callback(); return 1; }};
global.clearTimeout = () => {{}};
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
    const configured = investigationResponses?.[
      Math.min(investigationCallCount, investigationResponses.length - 1)
    ];
    investigationCallCount += 1;
    const status = configured?.status ?? investigationStatus;
    const body = configured?.body ?? investigationPayload;
    const headers = configured?.headers ?? investigationHeaders;
    return {{
      ok: status < 400,
      status,
      headers: {{
        get(name) {{
          return (
            headers[name]
            ?? headers[name.toLowerCase()]
            ?? null
          );
        }},
      }},
      json: async () => body,
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
  history: JSON.parse(sessionStorageState.get("workforce-chat:WFD") || "[]"),
  investigationCallCount,
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
@pytest.mark.asyncio
async def test_project_chat_is_accessible_and_csp_restricted() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert 'aria-labelledby="chat-title"' in response.text
    assert '<label for="manager-question">' in response.text
    assert 'aria-live="polite"' in response.text


@pytest.mark.ui
def test_chat_uses_selected_project_bounded_context_and_safe_dom() -> None:
    script = (WEB / "static" / "chat.js").read_text()
    assert "/api/v1/investigations?" in script
    assert "URLSearchParams" in script
    assert "project_key:state.project" in script
    assert ".textContent" in script
    assert "innerHTML" not in script
    assert 'payload.explanation.source!=="bedrock"' in script
    assert "previous_answer_context" in script
    assert "project_key=WRD" not in script


@pytest.mark.ui
def test_bedrock_chat_preserves_answer_and_hides_raw_citations() -> None:
    answer = (
        "WFD-13 is blocked by missing API approval.\n"
        "Focus on the approval queue before rebalancing the team."
    )

    result = _run_chat_runtime(
        investigation_payload={
            "explanation": {
                "answer": answer,
                "summary": "This shorter summary should never be shown.",
                "citations": ["jira:WFD-13:summary", "jira:WFD-13:status"],
                "source": "bedrock",
            }
        }
    )
    messages = cast(list[dict[str, str]], result["messages"])

    assert messages[-1]["className"] == "assistant-message"
    assert messages[-1]["text"] == answer
    assert "jira:WFD-13:summary" not in json.dumps(messages)
    assert "Evidence:" not in json.dumps(messages)


@pytest.mark.ui
def test_transient_bedrock_failures_wait_until_bedrock_succeeds() -> None:
    result = _run_chat_runtime(
        investigation_responses=[
            {
                "status": 503,
                "body": {
                    "error_code": "bedrock_timeout",
                    "correlation_id": "corr-timeout",
                    "message": "Bedrock timed out.",
                    "retryable": True,
                },
            },
            {
                "status": 503,
                "body": {
                    "error_code": "bedrock_throttling",
                    "correlation_id": "corr-throttled",
                    "message": "Bedrock throttled the request.",
                    "retryable": True,
                },
            },
            {
                "status": 200,
                "body": {
                    "explanation": {
                        "answer": "WFD-11 is blocked by WFD-9.",
                        "source": "bedrock",
                    }
                },
            },
        ]
    )
    messages = cast(list[dict[str, str]], result["messages"])

    assert result["investigationCallCount"] == 3
    assert messages[-1] == {
        "className": "assistant-message",
        "text": "WFD-11 is blocked by WFD-9.",
    }
    assert all("temporarily unavailable" not in item["text"] for item in messages)
