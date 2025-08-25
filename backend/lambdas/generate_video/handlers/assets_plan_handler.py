from typing import Any, Dict, List


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    plot = event.get("plot") or {}
    scenes: List[Dict[str, Any]] = plot.get("scenes") or []
    out = dict(event)
    out["scenes"] = scenes
    return out


