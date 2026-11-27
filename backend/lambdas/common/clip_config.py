"""Library clips on demand (docs/CLIPS_ON_DEMAND.md): the owner's live knobs.

ONE SSM parameter (CLIPS_CONFIG_PARAM, a JSON object), read with a short cache, exactly like the plans knobs (common/plans.py): the owner changes a limit or pulls the kill
switch without a deploy (`scripts/clips_admin.py config set <knob> <value>`). A missing, unreadable or invalid value falls back to DEFAULTS knob by knob, and in the
defaults generation is OFF.

Two switches must both be on before a single dollar is spent: the deploy flag CLIPS_ON_DEMAND=1 (stack context `clipsOnDemand`) and the knob `enabled`.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger()

PLANS_ALL = ("free", "pro", "max", "test")
GENERATE_PLANS = ("max", "test")   # code, not a knob: Free and Pro never generate, whatever the parameter says

# name: (default, kind, lowest, highest). Documented in docs/CLIPS_ON_DEMAND.md section 3.
KNOBS: Dict[str, tuple] = {
    "master_enabled": (True, "bool", None, None),           # the master kill switch: false stops generation of EVERY media type at once
    "enabled": (False, "bool", None, None),                 # the kill switch for CLIP generation
    "reuse_enabled": (True, "bool", None, None),            # library clips are offered to videos at all
    "reuse_plans": (list(PLANS_ALL), "plans", None, None),  # plans whose videos may use library clips
    "platform_day_usd": (10.0, "float", 0.0, 10000.0),      # every generation of paying accounts in one UTC day (hard stop)
    "platform_month_usd": (150.0, "float", 0.0, 100000.0),  # ... in one calendar month
    "test_day_usd": (2.0, "float", 0.0, 1000.0),            # the same for test and comped accounts (their own budget)
    "test_month_usd": (20.0, "float", 0.0, 10000.0),
    "account_cap_usd": (3.0, "float", 0.0, 100.0),          # ceiling over the formula, per paying account and calendar month
    "test_account_cap_usd": (3.0, "float", 0.0, 100.0),     # per test or comped account and calendar month
    "share": (0.5, "float", 0.0, 1.0),                      # the part of the remaining margin that may buy clips
    "floor_usd": (1.0, "float", 0.0, 100.0),                # what must remain per account per month whatever happens
    "credit_cost_usd": (0.20, "float", 0.0, 10.0),          # cost of one credit used for the reserve: the measured p90
    "credits_per_month": (120, "int", 1, 10000),            # the Max grant that is reserved in full from the first day
    "kept_usd_month": (30.83, "float", 0.0, 1000.0),        # kept per month from a monthly Max subscriber: the lowest (EU) storefront
    "kept_usd_year": (25.70, "float", 0.0, 1000.0),         # ... from a yearly one, per month
    "video_cap_clips": (2, "int", 0, 20),                   # generations per video
    "price_per_second_usd": (0.0695, "float", 0.0, 10.0),   # what the provider bills per second at 720p (it reports no dollar amount)
    "overhead_usd": (0.025, "float", 0.0, 1.0),             # around one generation: the provider's "thought" tokens (measured: about 1 cent), the gate, the checks, the embeddings
    "clip_seconds": (8, "int", 3, 15),
    "clip_seconds_long": (10, "int", 3, 15),                # for a beat longer than clip_seconds + 0.5
    "gen_timeout_s": (150, "int", 10, 280),                 # the provider call is abandoned after this
    "start_deadline_s": (60, "int", 0, 200),                # no generation starts later than this into the beat (0 = never generate inside a request)
    "search_min_score": (0.35, "float", 0.0, 1.0),          # a library clip below this (wording vs clip) is not even checked
    "reuse_min_score": (0.62, "float", 0.0, 1.0),           # brief vs a library clip's brief: at or above = "we already have this scene", nothing is generated
    "demand_join_score": (0.80, "float", 0.0, 1.0),         # two briefs this close are the same line of the demand log
    "min_demand": (1, "int", 1, 100),                       # distinct videos that must have asked for a brief before it is generated
    "tight_share": (0.5, "float", 0.0, 1.0),                # from this share of the day's budget spent ...
    "min_demand_tight": (2, "int", 1, 100),                 # ... only briefs asked for by this many videos are generated
    "gate_min_score": (7, "int", 0, 10),
    "model": ("gemini-omni-1.2-flash", "text", None, None),
    # ---- the account's share for clips inside the one allowance (images and objects below have theirs): section 2 of docs/LIBRARY_ON_DEMAND.md
    "clip_account_cap_usd": (1.75, "float", 0.0, 100.0),     # 3 generations of 8 s a month for a monthly Max account
    # ---- images (docs/LIBRARY_ON_DEMAND.md part A): the same OpenAI model and tier as the image catalog
    "image_enabled": (False, "bool", None, None),            # the kill switch for image generation
    "image_price_usd": (0.05, "float", 0.0, 5.0),            # one generation at 2048x1152 high with its check and embeddings (measured 0.0442 + 0.001)
    "image_account_cap_usd": (1.00, "float", 0.0, 100.0),
    "image_test_account_cap_usd": (1.00, "float", 0.0, 100.0),
    "image_video_cap": (4, "int", 0, 50),
    "image_day_usd": (3.0, "float", 0.0, 10000.0),
    "image_month_usd": (40.0, "float", 0.0, 100000.0),
    "image_test_day_usd": (1.0, "float", 0.0, 1000.0),
    "image_test_month_usd": (10.0, "float", 0.0, 10000.0),
    "image_timeout_s": (75, "int", 5, 240),
    "image_reuse_min_score": (0.62, "float", 0.0, 1.0),      # brief vs the catalog (text to image): at or above = we already have this picture
    "image_model": ("gpt-image-2.6-flare", "text", None, None),
    # ---- whiteboard sketch objects (part B): one call per video for all its missing objects
    "object_enabled": (False, "bool", None, None),
    "object_plans": (["max", "test"], "plans", None, None),  # plans whose whiteboard videos may have objects made (never Free)
    "object_call_usd": (0.04, "float", 0.0, 5.0),            # one sheet at 2048x1152 medium (measured 0.038)
    "object_gate_usd": (0.007, "float", 0.0, 1.0),           # the gate and naming call, per object
    "object_max_per_call": (6, "int", 1, 6),
    "object_account_cap_usd": (0.15, "float", 0.0, 100.0),
    "object_test_account_cap_usd": (0.30, "float", 0.0, 100.0),
    "object_video_cap": (1, "int", 0, 10),                   # calls per video
    "object_day_usd": (1.0, "float", 0.0, 10000.0),
    "object_month_usd": (10.0, "float", 0.0, 100000.0),
    "object_test_day_usd": (0.5, "float", 0.0, 1000.0),
    "object_test_month_usd": (5.0, "float", 0.0, 10000.0),
    "object_sure_score": (0.55, "float", 0.0, 1.0),          # a drawing found by MEANING below this score is not trusted: the asked drawing is made (a honeycomb is not a cheese)
    "object_timeout_s": (30, "int", 5, 120),                 # the plan step waits at most this long; later or rejected = the written label
}

_cache: Dict[str, Any] = {"at": 0.0, "raw": None}
_override: Optional[Dict[str, Any]] = None
_ssm = None


def flag() -> bool:
    """The deploy flag. Off (the default everywhere): nothing in this feature runs and nothing else changes."""
    return os.environ.get("CLIPS_ON_DEMAND", "0") == "1"


def set_config(values: Optional[Dict[str, Any]]) -> None:
    """Tests and scripts: use these raw values instead of the SSM parameter (None: back to the parameter)."""
    global _override
    _override = values
    _cache.update({"at": 0.0, "raw": None})


def coerce(name: str, value: Any) -> Any:
    """The clean value of one knob, or raises ValueError (the stored parameter: bad -> default; the admin script: bad -> refused)."""
    default, kind, lo, hi = KNOBS[name]
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "1", "on", "yes", "false", "0", "off", "no"):
            return value.strip().lower() in ("true", "1", "on", "yes")
        raise ValueError(f"{name} must be true or false")
    if kind in ("int", "float"):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a number")
        try:
            v = int(value) if kind == "int" else float(value)
            if kind == "int" and float(value) != v:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a {'whole ' if kind == 'int' else ''}number") from None
        if v != v or not (lo <= v <= hi):
            raise ValueError(f"{name} must be from {lo} to {hi}")
        return v
    if kind == "plans":
        if isinstance(value, str):
            value = [x for x in value.replace(",", " ").split() if x]
        if not isinstance(value, list) or not all(x in PLANS_ALL for x in value):
            raise ValueError(f"{name} must be a list of {', '.join(PLANS_ALL)}")
        return sorted(set(value))
    if kind == "text":
        if not isinstance(value, str) or not (1 <= len(value) <= 80) or not all(c.isalnum() or c in "-._" for c in value):
            raise ValueError(f"{name} must be a short identifier")
        return value
    raise ValueError(name)


def clean_config(raw: Any) -> Dict[str, Any]:
    out = {k: (list(v[0]) if isinstance(v[0], list) else v[0]) for k, v in KNOBS.items()}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        if k in KNOBS:
            try:
                out[k] = coerce(k, v)
            except ValueError as e:
                logger.error("CLIPS_CONFIG_INVALID %s (the default is used)", e)
    return out


def _read_raw() -> Dict[str, Any]:
    global _ssm
    name = os.environ.get("CLIPS_CONFIG_PARAM")
    if not name:
        return {}
    if _ssm is None:
        import boto3
        _ssm = boto3.client("ssm")
    try:
        return json.loads(_ssm.get_parameter(Name=name)["Parameter"]["Value"] or "{}")
    except _ssm.exceptions.ParameterNotFound:   # never set: every default, so generation is off
        return {}


def config(now: Optional[float] = None) -> Dict[str, Any]:
    """The knobs, cleaned. Cached for CLIPS_CONFIG_TTL seconds (default 60) per warm function. A read failure keeps the last good values; with none, the defaults (generation off)."""
    if _override is not None:
        return clean_config(_override)
    now = time.time() if now is None else now
    if _cache["raw"] is None or now - _cache["at"] > float(os.environ.get("CLIPS_CONFIG_TTL", "60")):
        try:
            _cache["raw"] = _read_raw()
        except Exception:   # noqa: BLE001 - the knobs must never stop a video
            logger.exception("CLIPS_CONFIG_READ_FAILED (keeping %s)", "the last good values" if _cache["raw"] is not None else "the defaults")
            _cache["raw"] = _cache["raw"] if _cache["raw"] is not None else {}
        _cache["at"] = now
    return clean_config(_cache["raw"])


def limits(cfg: Dict[str, Any], media: str, kind: str) -> Dict[str, float]:
    """The four limits of one media type for a paying ('paid') or a no-revenue ('test') account: generations per video, the account's share of the month for
    this type, and this type's day and month budgets. The account's TOTAL of the month (all types) is account_allowance_usd / test_account_cap_usd."""
    paid = kind == "paid"
    if media == "clip":
        return {"video_cap": cfg["video_cap_clips"], "account_cap": cfg["clip_account_cap_usd"] if paid else cfg["test_account_cap_usd"],
                "day": cfg["platform_day_usd"] if paid else cfg["test_day_usd"], "month": cfg["platform_month_usd"] if paid else cfg["test_month_usd"]}
    if media not in ("image", "object"):
        raise ValueError(media)
    return {"video_cap": cfg[f"{media}_video_cap"], "account_cap": cfg[f"{media}_account_cap_usd" if paid else f"{media}_test_account_cap_usd"],
            "day": cfg[f"{media}_day_usd" if paid else f"{media}_test_day_usd"], "month": cfg[f"{media}_month_usd" if paid else f"{media}_test_month_usd"]}


def generation_on(cfg: Optional[Dict[str, Any]] = None) -> bool:
    return flag() and bool((config() if cfg is None else cfg)["enabled"])


def price_usd(seconds: float, cfg: Optional[Dict[str, Any]] = None) -> float:
    """What one generation of `seconds` is charged to the budgets."""
    cfg = config() if cfg is None else cfg
    return round(float(seconds) * float(cfg["price_per_second_usd"]) + float(cfg["overhead_usd"]), 6)


def account_allowance_usd(interval: Optional[str], credits_used: int, cfg: Optional[Dict[str, Any]] = None) -> float:
    """The month's clip allowance of a PAYING Max account (docs/CLIPS_ON_DEMAND.md 2.2):
    min(cap, share x (kept - floor - credit cost x max(grant, credits used this month))), never below zero.
    The whole grant is reserved at the high cost from the first day, so kept - credits - clips >= floor holds however the month goes; credits used above the grant
    (rolled-over ones) shrink it further."""
    cfg = config() if cfg is None else cfg
    kept = float(cfg["kept_usd_year"] if interval == "year" else cfg["kept_usd_month"])
    reserved = float(cfg["credit_cost_usd"]) * max(int(cfg["credits_per_month"]), int(credits_used or 0))
    return round(max(0.0, min(float(cfg["account_cap_usd"]), float(cfg["share"]) * (kept - float(cfg["floor_usd"]) - reserved))), 6)
