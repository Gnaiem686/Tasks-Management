from __future__ import annotations

import asyncio
import importlib
import json
import os
from typing import Any, cast

from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.fallback import DeterministicFallbackProvider
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
    """Use Bedrock when explicitly configured and fail safely to rules otherwise."""
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id:
        if os.getenv("BEDROCK_ONLY_CHAT", "false").casefold() == "true":
            raise RuntimeError("Bedrock chat model is not configured")
        return DeterministicFallbackProvider()

    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    boto3 = importlib.import_module("boto3")
    client = cast(Any, boto3).client("bedrock-runtime", region_name=region)

    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        def call() -> str:
            try:
                response = client.converse(
                    modelId=model_id,
                    system=[{"text": system_prompt}],
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": (
                                        "Explain this validated deterministic result. "
                                        "Submit the answer with the required tool:\n"
                                        + json.dumps(payload, sort_keys=True)
                                    )
                                }
                            ],
                        }
                    ],
                    toolConfig={
                        "tools": [
                            {
                                "toolSpec": {
                                    "name": EXPLANATION_TOOL_NAME,
                                    "description": (
                                        "Submit a validated workforce-risk explanation"
                                    ),
                                    "inputSchema": {"json": EXPLANATION_TOOL_SCHEMA},
                                }
                            }
                        ],
                        "toolChoice": {"tool": {"name": EXPLANATION_TOOL_NAME}},
                    },
                    inferenceConfig={"temperature": 0, "maxTokens": 900},
                )
                content = response["output"]["message"]["content"]
                tool_input = next(
                    block["toolUse"]["input"]
                    for block in content
                    if block.get("toolUse", {}).get("name") == EXPLANATION_TOOL_NAME
                )
                return json.dumps(tool_input)
            except Exception as error:
                raise OSError("Bedrock explanation invocation failed") from error

        return await asyncio.to_thread(call)

    return BedrockExplanationProvider(
        invoke=invoke,
        allow_fallback=(os.getenv("BEDROCK_ONLY_CHAT", "false").casefold() != "true"),
    )
