"""Plans (docs/PLANS.md): THE one place that says what Free, Pro and Max are, and the owner's runtime knobs that contain the cost of the free plan.

  PLANS            the ladder approved on 2026-11-27 (limits, credits, rights). Everything else (launcher, wallet, capabilities, library, watermark) reads it from here.
  config()         the knobs, read from ONE SSM parameter (PLANS_CONFIG_PARAM, a JSON object) with a short cache, so the owner changes them without a deploy
                   (`scripts/plans_admin.py config set <knob> <value>`). A missing, unreadable or invalid value falls back to DEFAULTS, knob by knob.
  rights(plan)     what a plan may do right now (the Free plan's length and resolution come from the knobs).
  check_create()   the launcher's enforcement of length, resolution and photos; PlanError carries the localized 403.

Switched on by the stack (PLANS_ENABLED=1, backend/plans_feature.py; `-c plans=0` removes it). Off: nothing here is consulted and every account behaves as before.
No store purchases yet: `PURCHASES_LIVE` is False, so every answer says `can_upgrade: false` (phase 2, docs/PLANS.md).
"""
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger()

PURCHASES_LIVE = False   # phase 2 flips this (store verification and webhooks exist); until then no app may show a buy button
GB = 1_000_000_000
ORDER = ("free", "pro", "max")

# The approved ladder. `max_seconds` of Free is the plan's ceiling; the ACTIVE free cap is the knob `free_max_seconds` (rights()).
PLANS: Dict[str, Dict[str, Any]] = {
    "free": {"id": "free", "name": "Free", "rank": 0, "credits_per_month": 0, "rollover_months": 0, "credits_cap": 0, "max_seconds": 60,
             "resolutions": ["720p", "1080p"], "watermark_modes": ["videomk"], "watermark_forced": True, "storage_bytes": 2 * GB, "photos_per_video": 10,
             "priority_queue": False, "premium_looks": False, "commercial_use": False},
    "pro": {"id": "pro", "name": "Pro", "rank": 1, "credits_per_month": 30, "rollover_months": 0, "credits_cap": 30, "max_seconds": 300,
            "resolutions": ["720p", "1080p"], "watermark_modes": ["none", "videomk", "moments"], "watermark_forced": False, "storage_bytes": 100 * GB, "photos_per_video": 30,
            "priority_queue": False, "premium_looks": False, "commercial_use": True},
    "max": {"id": "max", "name": "Max", "rank": 2, "credits_per_month": 120, "rollover_months": 1, "credits_cap": 240, "max_seconds": 720,
            "resolutions": ["720p", "1080p", "2160p"], "watermark_modes": ["none", "videomk", "moments", "custom"], "watermark_forced": False, "storage_bytes": 300 * GB, "photos_per_video": 60,
            "priority_queue": True, "premium_looks": True, "commercial_use": True},
}
# What the apps need to show a paywall later (docs/PLANS_PROPOSAL_2026-11-27.md section 5.6). Prices are the US base; the stores are the source of truth once products exist.
PRICES_USD = {"pro": {"monthly": 14.99, "yearly": 149.99}, "max": {"monthly": 39.99, "yearly": 399.99}}
PRODUCTS = {
    "pro": {"apple": {"monthly": "com.videomk.app.pro.monthly", "yearly": "com.videomk.app.pro.yearly"}, "google": {"subscription": "videomk_pro", "monthly": "monthly", "yearly": "yearly"},
            "web": {"monthly": "pro_monthly", "yearly": "pro_yearly"}},
    "max": {"apple": {"monthly": "com.videomk.app.max.monthly", "yearly": "com.videomk.app.max.yearly"}, "google": {"subscription": "videomk_max", "monthly": "monthly", "yearly": "yearly"},
            "web": {"monthly": "max_monthly", "yearly": "max_yearly"}},
}
RESOLUTION_ORDER = ("720p", "1080p", "2160p")

# ----------------------------------------------------------------------------- the knobs
# name: (default, kind, lowest, highest). Documented one by one in docs/PLANS.md ("Config knobs"); `scripts/plans_admin.py config` shows and sets them.
KNOBS: Dict[str, tuple] = {
    "enforce": (True, "bool", None, None),                       # the plan limits at the launcher (length, resolution, watermark, photos). False: limits are reported but not enforced
    "free_max_seconds": (30, "int", 15, 720),                    # longest video a Free account may make
    "free_max_resolution": ("1080p", "resolution", None, None),  # highest resolution on Free
    "welcome_credits": (2, "int", 0, 50),                        # one-time welcome allowance (0 = none)
    "welcome_valid_days": (30, "int", 1, 365),
    "free_daily_credits": (0, "int", 0, 10),                     # the recurring free credit (0 = off)
    "free_credit_cadence": ("daily", "cadence", None, None),     # 'daily', or 'weekly' = at most free_credits_per_week claim days in a calendar week
    "free_credits_per_week": (3, "int", 1, 7),
    "free_daily_budget_credits": (15, "int", 0, 1_000_000),      # ALL free credits spent by ALL accounts in one UTC day; reached = free creation pauses until 00:00 UTC. 0 = no free creation at all
    "free_budget_unlimited": (False, "bool", None, None),        # True switches the global budget off (no ceiling)
    "cost_per_credit_usd": (0.15, "float", 0.0, 10.0),           # measured p50 (docs/PLANS_PROPOSAL_2026-11-27.md): only used to SHOW dollars next to credits
    "free_monthly_videos_cap": (0, "int", 0, 1000),              # per account and calendar month (UTC), videos paid with free credits. 0 = no cap
    "free_web": (False, "bool", None, None),                     # may the WEB grant or spend free credits? (a browser cannot be attested)
    "require_device_proof": (None, "bool", None, None),          # None = the stage default (PLANS_REQUIRE_DEVICE_PROOF_DEFAULT: 1 in production, 0 elsewhere)
    "device_proof_ios": (True, "bool", None, None),              # accept iOS App Attest (needs the device API deployed: -c deviceProof=1)
    "device_check_ios": (False, "bool", None, None),             # Apple DeviceCheck's two bits (needs the owner's DeviceCheck key: not available yet)
    "device_proof_android": (False, "bool", None, None),         # Play Integrity (needs the Play Console link and a service account: not available yet)
    "device_pass_minutes": (15, "int", 1, 1440),                 # how long one verified proof lets the account spend free credits
    "block_disposable_email": (True, "bool", None, None),
    "email_domain_deny": ([], "domains", None, None),            # extra domains that get no free allowance
    "email_domain_allow": ([], "domains", None, None),           # domains taken OUT of the shipped disposable list
    "claims_per_ip_day": (3, "int", 0, 100000),                  # free allowances claimed from one IP address in a UTC day (0 = no limit)
    "claims_per_ip_block_day": (10, "int", 0, 100000),           # ... from one /24 (IPv4) or /48 (IPv6)
    "signups_per_ip_hour": (5, "int", 0, 100000),                # accounts first seen from one IP address in an hour
    "claim_retention_days": (730, "int", 30, 3650),              # how long a free-allowance claim (a salted hash, nothing else) is kept
}
CADENCES = ("daily", "weekly")

_cache: Dict[str, Any] = {"at": 0.0, "raw": None}
_override: Optional[Dict[str, Any]] = None
_ssm = None


def enabled() -> bool:
    return os.environ.get("PLANS_ENABLED", "0") == "1"


def set_config(values: Optional[Dict[str, Any]]) -> None:
    """Tests and scripts: use these raw values instead of the SSM parameter (None: back to the parameter)."""
    global _override
    _override = values
    _cache.update({"at": 0.0, "raw": None})


def _coerce(name: str, value: Any) -> Any:
    """The clean value of one knob, or raises ValueError. Used for the stored parameter (bad -> default) and by the admin script (bad -> refused)."""
    default, kind, lo, hi = KNOBS[name]
    if kind == "bool":
        if value is None and default is None:
            return None
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
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number") from None
        if kind == "int" and float(value) != v:
            raise ValueError(f"{name} must be a whole number")
        if not (lo <= v <= hi):
            raise ValueError(f"{name} must be from {lo} to {hi}")
        return v
    if kind == "resolution":
        if value not in RESOLUTION_ORDER:
            raise ValueError(f"{name} must be one of {', '.join(RESOLUTION_ORDER)}")
        return value
    if kind == "cadence":
        if value not in CADENCES:
            raise ValueError(f"{name} must be one of {', '.join(CADENCES)}")
        return value
    if kind == "domains":
        if isinstance(value, str):
            value = [x for x in value.replace(",", " ").split() if x]
        if not isinstance(value, list) or len(value) > 2000 or not all(isinstance(x, str) and 3 <= len(x) <= 253 and "." in x and "@" not in x for x in value):
            raise ValueError(f"{name} must be a list of domain names")
        return sorted({x.strip().lower() for x in value})
    raise ValueError(name)


def clean_config(raw: Any) -> Dict[str, Any]:
    out = {k: (list(v[0]) if isinstance(v[0], list) else v[0]) for k, v in KNOBS.items()}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        if k in KNOBS:
            try:
                out[k] = _coerce(k, v)
            except ValueError as e:
                logger.error("PLANS_CONFIG_INVALID %s (the default is used)", e)
    if out["require_device_proof"] is None:
        out["require_device_proof"] = os.environ.get("PLANS_REQUIRE_DEVICE_PROOF_DEFAULT", "1") != "0"   # unset: the strict answer
    return out


def _read_raw() -> Dict[str, Any]:
    global _ssm
    name = os.environ.get("PLANS_CONFIG_PARAM")
    if not name:
        return {}
    if _ssm is None:
        import boto3
        _ssm = boto3.client("ssm")
    return json.loads(_ssm.get_parameter(Name=name)["Parameter"]["Value"] or "{}")


def config(now: Optional[float] = None) -> Dict[str, Any]:
    """The knobs, cleaned. Cached for PLANS_CONFIG_TTL seconds (default 60) per warm function; a read failure keeps the last good values (or the defaults)."""
    if _override is not None:
        return clean_config(_override)
    now = time.time() if now is None else now
    ttl = float(os.environ.get("PLANS_CONFIG_TTL", "60"))
    if _cache["raw"] is None or now - _cache["at"] > ttl:
        try:
            _cache["raw"] = _read_raw()
        except Exception:   # noqa: BLE001 - the knobs must never stop a request
            logger.exception("PLANS_CONFIG_READ_FAILED (keeping %s)", "the last good values" if _cache["raw"] is not None else "the defaults")
            _cache["raw"] = _cache["raw"] if _cache["raw"] is not None else {}
        _cache["at"] = now
    return clean_config(_cache["raw"])


# ----------------------------------------------------------------------------- rights
def rights(plan: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What `plan` may do now: the definition, with the Free plan's length and resolution taken from the knobs."""
    out = dict(PLANS.get(plan) or PLANS["free"])
    out["resolutions"], out["watermark_modes"] = list(out["resolutions"]), list(out["watermark_modes"])
    if out["id"] == "free":
        cfg = config() if cfg is None else cfg
        out["max_seconds"] = int(cfg["free_max_seconds"])
        top = RESOLUTION_ORDER.index(cfg["free_max_resolution"])
        out["resolutions"] = [r for r in RESOLUTION_ORDER if RESOLUTION_ORDER.index(r) <= top and r != "2160p"] or ["720p"]
    return out


def lowest_plan(test, cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The cheapest plan whose rights pass `test` (what an upgrade prompt names), or None when no plan allows it."""
    for p in ORDER:
        if test(rights(p, cfg)):
            return p
    return None


def usd(credits: float, cfg: Optional[Dict[str, Any]] = None) -> float:
    cfg = config() if cfg is None else cfg
    return round(float(credits) * float(cfg["cost_per_credit_usd"]), 2)


class PlanError(Exception):
    """A refusal by plan: HTTP status, stable `code`, the message key (common/i18n) and what the apps need for the upgrade prompt."""

    def __init__(self, code: str, key: str, *, status: int = 403, plan: str = "free", requires_plan: Optional[str] = None, feature: str = "", limit: Optional[Dict[str, Any]] = None, **params: Any):
        super().__init__(code)
        self.code, self.key, self.status, self.plan, self.requires_plan, self.feature, self.limit, self.params = code, key, status, plan, requires_plan, feature, limit or {}, params

    def body(self, locale: Optional[str]) -> Dict[str, Any]:
        from common import i18n
        names = {"plan_name": PLANS[self.requires_plan]["name"] if self.requires_plan else ""}
        key = self.key if self.requires_plan or f"{self.key}.top" not in i18n.EN else f"{self.key}.top"   # nothing to upgrade to: say only the limit
        return {"code": self.code, "message": i18n.t(key, locale, **{**names, **self.params}), "feature": self.feature, "plan": self.plan, "requires_plan": self.requires_plan,
                "limit": self.limit, "can_upgrade": PURCHASES_LIVE}


def _minutes_text(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def check_create(options: Dict[str, Any], plan: str, cfg: Optional[Dict[str, Any]] = None, *, default_minutes: float = 3.0) -> None:
    """The launcher's plan gate for one create request (raises PlanError; changes `options` only to pick a default the plan allows).
    Length: an explicit length over the plan's longest video is refused; no length given = the server default, shortened to the plan's longest.
    Resolution: an explicit one the plan lacks is refused; none given = the default, or the plan's best when the default is above it.
    Photos: more than the plan's photos per video is refused. Premium looks: `premium_looks: true` is added for plans that have them (the engine reads it)."""
    cfg = config() if cfg is None else cfg
    r = rights(plan, cfg)
    if not cfg["enforce"]:
        return
    cap = int(r["max_seconds"])
    asked = options.get("target_minutes")
    if asked is None:
        options["target_minutes"] = min(float(default_minutes), cap / 60.0)
    elif float(asked) * 60.0 > cap + 1e-6:
        need = lowest_plan(lambda x: float(asked) * 60.0 <= x["max_seconds"] + 1e-6, cfg)
        raise PlanError("plan_length", "plan.length", plan=plan, requires_plan=need, feature="length", limit={"max_seconds": cap, "max_minutes": round(cap / 60.0, 4)}, max=_minutes_text(cap))
    res = options.get("resolution")
    if res is None:
        if "1080p" not in r["resolutions"]:
            options["resolution"] = r["resolutions"][-1]
    elif res not in r["resolutions"]:
        need = lowest_plan(lambda x: res in x["resolutions"], cfg)
        raise PlanError("plan_resolution", "plan.resolution", plan=plan, requires_plan=need, feature="resolution", limit={"resolutions": r["resolutions"]}, resolution="4K" if res == "2160p" else res)
    photos = len(options.get("media") or []) + len(options.get("library_media") or [])
    if photos > int(r["photos_per_video"]):
        need = lowest_plan(lambda x: photos <= x["photos_per_video"], cfg)
        raise PlanError("plan_photos", "plan.photos", plan=plan, requires_plan=need, feature="photos", limit={"photos_per_video": r["photos_per_video"]}, max=r["photos_per_video"])
    if r["premium_looks"]:
        options["premium_looks"] = True


def public_limits(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"max_seconds": r["max_seconds"], "max_minutes": round(r["max_seconds"] / 60.0, 4), "resolutions": r["resolutions"], "watermark_modes": r["watermark_modes"],
            "watermark_forced": r["watermark_forced"], "storage_bytes": r["storage_bytes"], "photos_per_video": r["photos_per_video"], "priority_queue": r["priority_queue"],
            "premium_looks": r["premium_looks"], "commercial_use": r["commercial_use"], "credits_per_month": r["credits_per_month"], "rollover_months": r["rollover_months"],
            "credits_cap": r["credits_cap"]}


def locked(plan: str, cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """What this plan cannot do and the cheapest plan that can: the apps put that plan's name on the tile (for example 'Max' on 4K) and open the paywall there."""
    cfg = config() if cfg is None else cfg
    mine, out = rights(plan, cfg), []
    longest = mine["max_seconds"]
    for p in ORDER[ORDER.index(mine["id"]) + 1:]:
        theirs = rights(p, cfg)
        seen = {(x["feature"], str(x.get("value"))) for x in out}

        def add(feature: str, value: Any, **extra: Any) -> None:
            if (feature, str(value)) not in seen:
                out.append({"feature": feature, "value": value, "requires_plan": p, **extra})
        if theirs["max_seconds"] > longest:   # "videos longer than over_seconds, up to max_seconds, need this plan"
            add("length", theirs["max_seconds"], over_seconds=longest, max_seconds=theirs["max_seconds"])
            longest = theirs["max_seconds"]
        for res in theirs["resolutions"]:
            if res not in mine["resolutions"]:
                add("resolution", res)
        for mode in theirs["watermark_modes"]:
            if mode not in mine["watermark_modes"]:
                add("watermark", mode)
        if theirs["storage_bytes"] > mine["storage_bytes"]:
            add("storage", theirs["storage_bytes"])
        if theirs["photos_per_video"] > mine["photos_per_video"]:
            add("photos", theirs["photos_per_video"])
        for flag in ("priority_queue", "premium_looks", "commercial_use"):
            if theirs[flag] and not mine[flag]:
                add(flag, True)
    return out


def catalog(cfg: Optional[Dict[str, Any]] = None, locale: Optional[str] = None) -> List[Dict[str, Any]]:
    """The three plans as the paywall needs them (ids, numbers, product ids). Prices are indicative until the stores answer."""
    cfg = config() if cfg is None else cfg
    out = []
    for p in ORDER:
        r = rights(p, cfg)
        out.append({"id": p, "name": r["name"], "rank": r["rank"], "limits": public_limits(r), **({"price_usd": PRICES_USD[p], "products": PRODUCTS[p]} if p in PRICES_USD else {})})
    return out
