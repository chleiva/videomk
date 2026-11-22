"""API-key lookup.

Prefers SSM Parameter Store (standard parameters are free, so the account has no
idle secret cost) and falls back to Secrets Manager for existing deployments.
Values are cached per Lambda container.
"""
import json
import logging
import os
from typing import Dict

import boto3

_cache: Dict[str, str] = {}


def _from_secret_string(raw: str) -> str:
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return str(payload.get("API_KEY") or payload.get("openai_api_key") or "")
    except json.JSONDecodeError:
        pass
    return raw.strip()


def get_openai_api_key() -> str:
    if "openai" in _cache:
        return _cache["openai"]

    key = ""
    param = os.environ.get("OPENAI_SSM_PARAM", "/videomk/openai_api_key")
    try:
        res = boto3.client("ssm").get_parameter(Name=param, WithDecryption=True)
        key = _from_secret_string(res["Parameter"]["Value"])
    except Exception as e:  # missing parameter / no permission -> fall back
        logging.info("SSM parameter %s unavailable (%s); trying Secrets Manager", param, type(e).__name__)

    if not key:
        name = os.environ.get("OPENAI_API_SECRET_NAME", "OPENAI_API_KEY")
        try:
            res = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2")).get_secret_value(SecretId=name)
            key = _from_secret_string(res.get("SecretString") or "")
        except Exception as e:
            logging.error("Could not read OpenAI API key (%s)", type(e).__name__)

    if key:
        _cache["openai"] = key
    return key


def get_secret_param(name: str, quiet: bool = False) -> str:
    """Generic SSM SecureString lookup (cached per container), e.g. '/videomk/gemini_api_key'."""
    if name in _cache:
        return _cache[name]
    try:
        val = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except Exception as e:
        (logging.info if quiet else logging.error)("could not read %s (%s)", name, type(e).__name__)
        return ""
    val = _from_secret_string(val)
    if val:
        _cache[name] = val
    return val
