from __future__ import annotations

import asyncio
import importlib
import json
import os
from typing import Any, cast

from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.protocol import ExplanationProvider

EXPLANATION_TOOL_NAME = "submit_workforce_explanation"
EXPLANATION_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "root_causes": {"type": "array", "items": {"type": "string"}},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "candidate_id": {"type": ["string", "null"]},
                },
                "required": ["action", "reason", "candidate_id"],
            },
        },
        "citations": {"type": "array", "items": {"type": "string"}},
        "score": {"type": ["integer", "null"]},
        "risk_level": {"type": ["string", "null"]},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "answer",
        "summary",
        "root_causes",
        "recommendations",
        "citations",
        "score",
        "risk_level",
        "uncertainties",
    ],
}


def get_explanation_provider() -> ExplanationProvider:
    """Return the Bedrock-only provider used for successful chat responses."""
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id:
        raise RuntimeError("Bedrock chat model is not configured")

    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    boto3 = importlib.import_module("boto3")
    client = cast(Any, boto3).client("bedrock-runtime", region_name=region)

    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        def call() -> str:
            try:
                grounding_directive = _grounding_directive(payload)
                planning_call = "select evidence categories" in system_prompt.casefold()
                request_instruction = (
                    "Return only the requested JSON evidence plan. Do not answer "
                    "the manager's question.\n"
                    if planning_call
                    else (
                        grounding_directive
                        + "\nAnswer the manager's question naturally using only "
                        "this validated project evidence:\n"
                    )
                )
                response = client.converse(
                    modelId=model_id,
                    system=[{"text": system_prompt}],
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": (
                                        request_instruction
                                        + json.dumps(payload, sort_keys=True)
                                    )
                                }
                            ],
                        }
                    ],
                    inferenceConfig={"temperature": 0, "maxTokens": 900},
                )
                content = response["output"]["message"]["content"]
                text = "".join(str(block.get("text", "")) for block in content).strip()
                if not text:
                    raise ValueError("Bedrock returned an empty answer")
                return text
            except Exception as error:
                raise OSError(
                    "Bedrock explanation invocation failed: "
                    f"{type(error).__name__}: {error}"
                ) from error

        return await asyncio.to_thread(call)

    return BedrockExplanationProvider(
        invoke=invoke,
        allow_fallback=False,
        max_attempts=3,
        persistent_retry=True,
    )


def _grounding_directive(payload: dict[str, object]) -> str:
    required_keys: list[str] = []
    task_query = payload.get("task_query")
    if isinstance(task_query, dict):
        tasks = task_query.get("tasks")
        if isinstance(tasks, list):
            required_keys.extend(
                str(task["key"])
                for task in tasks
                if isinstance(task, dict) and task.get("key")
            )
    previous = payload.get("previous_answer_context")
    if isinstance(previous, dict):
        issues = previous.get("issues")
        if isinstance(issues, list):
            required_keys.extend(
                str(issue["key"])
                for issue in issues
                if isinstance(issue, dict) and issue.get("key")
            )
    required_keys = list(dict.fromkeys(required_keys))
    if not required_keys:
        return "Do not add project facts that are absent from the evidence."
    return (
        "Mandatory grounding: explicitly include every one of these Jira issue "
        f"keys in the answer: {', '.join(required_keys)}. Do not omit any key."
    )
