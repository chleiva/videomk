import json
from typing import Any, Dict, List, Optional

import boto3


_bedrock = boto3.client("bedrock-runtime")



def invoke_anthropic(
    messages: List[Dict[str, str]],
    *,
    model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
    max_tokens: int = 512,
    temperature: float = 0.2,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke an Anthropic model on Bedrock and return the raw response JSON.

    Note: Bedrock returns a JSON envelope where the model text is typically in
    response["content"][0]["text"]. We expose the raw structure so callers can
    decide how to parse it.
    """
    body: Dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system

    res = _bedrock.invoke_model(modelId=model_id, body=json.dumps(body))
    return json.loads(res["body"].read())


def response_text(response: Dict[str, Any]) -> str:
    """Extract primary text from a Bedrock Anthropic response."""
    content = response.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            return str(first["text"])
    # Some variants may include different fields; fallback to stringifying
    return json.dumps(response)


