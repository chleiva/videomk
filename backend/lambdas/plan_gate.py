"""The launcher's side of plans (docs/PLANS.md): what a create request (and a retry) must pass before a video starts, in one place so sf_launcher and video_retry stay small.

  begin(user, event)        -> Gate or None (plans off: None, and every function below is a no-op that behaves as before plans)
  check(gate, options, ...) -> None or the 403 (plan_length, plan_resolution, plan_photos)
  charge(gate, ...)         -> (the wallet breakdown, None) or (None, the response): 402 insufficient_credits, 403 free_not_available, 429 free_budget_spent / free_monthly_cap
  give_back(gate)           the video did not start: the free budget and the monthly counter get their share back
  record(gate)              what the video row keeps for the reports: plan, free_credits, priority

The order inside charge() matters for the owner's ceiling: the credits are taken from the wallet first, then the free ones among them must fit in today's global budget
(one atomic counter for all accounts) and in the account's monthly cap; if they do not, the wallet gets everything back and nothing starts.
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from common import entitlements, free_grants, i18n, plans, wallet
from common.http import json_response

logger = logging.getLogger()


class Gate:
    def __init__(self, user: str, event: Any):
        self.user = user
        self.cfg = plans.config()
        self.ctx = free_grants.context(event)
        self.ent = entitlements.effective(user)
        self.plan = self.ent["plan"]
        self.rights = plans.rights(self.plan, self.cfg)
        self.free_credits = 0
        self.monthly_taken = False


def begin(user: str, event: Any) -> Optional[Gate]:
    return Gate(user, event) if plans.enabled() else None


def check(gate: Optional[Gate], options: Dict[str, Any], loc: str, *, explicit_length: bool, default_minutes: float) -> Optional[Dict[str, Any]]:
    if gate is None:
        return None
    if not explicit_length and options.get("target_minutes") is not None and gate.cfg["enforce"]:   # a length the server chose (a deck's suggestion): shortened, never refused
        options["target_minutes"] = min(float(options["target_minutes"]), gate.rights["max_seconds"] / 60.0)
    try:
        plans.check_create(options, gate.plan, gate.cfg, default_minutes=default_minutes)
    except plans.PlanError as e:
        logger.info("PLAN_REFUSED code=%s plan=%s user=%s", e.code, gate.plan, gate.user)
        free_grants.emit("PlanRefused", Code=e.code)
        return json_response(e.status, e.body(loc))
    return None


def free_refusal(reason: str, loc: str, gate: Gate, status: int = 403, **extra: Any) -> Dict[str, Any]:
    """The client learns one of four things, never the rule behind it: app_only, not_available, paused, monthly_cap."""
    public = {"web": "app_only", "budget": "paused", "monthly_cap": "monthly_cap"}.get(reason, "not_available")
    code = {"paused": "free_budget_spent", "monthly_cap": "free_monthly_cap"}.get(public, "free_not_available")
    return json_response(status, {"code": code, "reason": public, "message": i18n.t(f"plan.free.{public}", loc), "plan": gate.plan, "requires_plan": "pro", "can_upgrade": plans.PURCHASES_LIVE, **extra},
                         {"Retry-After": "3600"} if status == 429 else None)


def charge(gate: Optional[Gate], user: str, credits: int, loc: str, *, tz: Optional[str]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """Plans on only (the callers keep their own code for plans off). InsufficientCredits is left to the caller, which already answers it."""
    assert gate is not None
    try:
        charged = wallet.charge(user, credits, tz=tz, ctx=gate.ctx)
    except wallet.FreeNotAvailable as e:
        logger.info("FREE_SPEND result=refused reason=%s user=%s", e.reason, user)
        free_grants.emit("FreeSpendRefused", Reason=e.reason)
        return None, free_refusal(e.reason, loc, gate)
    free_n = free_grants.free_credits_in(charged) if gate.plan == "free" and not gate.ent["unlimited"] else 0
    if free_n:
        now_cfg = gate.cfg
        if int(now_cfg["free_monthly_videos_cap"]) > 0 and not free_grants.monthly_take(user, now_cfg):
            wallet.refund(user, charged)
            free_grants.emit("FreeSpendRefused", Reason="monthly_cap")
            free_grants.stat("cap_refused", time.time())
            return None, free_refusal("monthly_cap", loc, gate, 429)
        gate.monthly_taken = int(now_cfg["free_monthly_videos_cap"]) > 0
        if not free_grants.budget_take(free_n, now_cfg):
            wallet.refund(user, charged)
            if gate.monthly_taken:
                free_grants.monthly_return(user)
                gate.monthly_taken = False
            logger.warning("FREE_BUDGET_SPENT user=%s credits=%s", user, free_n)
            free_grants.emit("FreeBudgetRefused")
            free_grants.stat("budget_refused", time.time())
            return None, free_refusal("budget", loc, gate, 429, resumes_at=free_grants.budget_state(now_cfg)["resumes_at"])
        gate.free_credits = free_n
    return charged, None


def give_back(gate: Optional[Gate]) -> None:
    if gate is None:
        return
    if gate.free_credits:
        free_grants.budget_return(gate.free_credits)
        gate.free_credits = 0
    if gate.monthly_taken:
        free_grants.monthly_return(gate.user)
        gate.monthly_taken = False


def record(gate: Optional[Gate], credits: int) -> Dict[str, Any]:
    """Attributes for the video row, and the metrics of one started video."""
    if gate is None:
        return {}
    kind = "test" if gate.ent["unlimited"] else gate.plan
    free_grants.emit("VideosStarted", Plan=kind)
    if gate.free_credits:
        free_grants.emit("FreeCreditsSpent", gate.free_credits)
    if credits - gate.free_credits > 0 and kind != "test":
        free_grants.emit("PaidCreditsSpent", credits - gate.free_credits)
    return {"plan": kind, "free_credits": gate.free_credits, **({"priority": 1} if gate.rights["priority_queue"] else {})}
