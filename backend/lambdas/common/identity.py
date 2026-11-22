from typing import Any, Dict, Optional


def extract_cognito_sub(event: Dict[str, Any]) -> Optional[str]:
    """Return the authenticated Cognito subject from an API Gateway proxy event.

    Supports REST API (authorizer.claims) and HTTP API (authorizer.jwt.claims).
    Never falls back to client-controlled values (path/body/headers).
    """
    try:
        authz = ((event or {}).get("requestContext") or {}).get("authorizer") or {}
        for claims in (authz.get("claims"), (authz.get("jwt") or {}).get("claims")):
            if isinstance(claims, dict):
                sub = claims.get("sub") or claims.get("cognito:username")
                if sub:
                    return str(sub)
    except Exception:
        pass
    return None
