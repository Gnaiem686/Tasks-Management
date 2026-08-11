from __future__ import annotations

import asyncio
import importlib
import json
import os
from typing import Any, cast

from agent_api.llm.bedrock import BedrockExplanationProvider
from agent_api.llm.fallback import DeterministicFallbackProvider
from agent_api.llm.protocol import ExplanationProvider


def get_explanation_provider() -> ExplanationProvider:
    """Use Bedrock when explicitly configured and fail safely to rules otherwise."""
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id:
        return DeterministicFallbackProvider()

    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    boto3 = importlib.import_module("boto3")
    client = cast(Any, boto3).client("bedrock-runtime", region_name=region)

    async def invoke(system_prompt: str, payload: dict[str, object]) -> str:
        def call() -> str:
            response = client.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "Explain this validated deterministic result and "
                                    "return only JSON:\n"
                                    + json.dumps(payload, sort_keys=True)
                                )
                            }
                        ],
                    }
                ],
                inferenceConfig={"temperature": 0, "maxTokens": 900},
            )
            return str(response["output"]["message"]["content"][0]["text"])

        return await asyncio.to_thread(call)

    return BedrockExplanationProvider(invoke=invoke)
