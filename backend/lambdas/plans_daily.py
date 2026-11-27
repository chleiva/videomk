"""Once a day (EventBridge, 00:20 UTC): yesterday's free and paid usage as CloudWatch metrics in `videomk/Plans` (docs/PLANS.md, "Measurement").

  FreeVideosDay, PaidVideosDay, FreeUsersDay, FreeCreditsDay, FreeCostTrackedUsdDay, FreeCostEstimatedUsdDay, FreeCostPerUserUsdDay, ClaimsGrantedDay, ClaimsRefusedDay
The alarm on FreeCostEstimatedUsdDay is defined in backend/plans_feature.py (no action attached: there is no notification topic yet). Read only: the videos table (a scan
filtered by day) and two counters of the usage table. The same numbers, with the top free users and the abuse tables, come from `scripts/plans_admin.py report`.
"""
import json
import logging
import time
from typing import Any, Dict

from common import free_grants, plan_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    day = (event or {}).get("day") or time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
    counters = plan_report.day_counters(day)
    rep = plan_report.summarize(day, plan_report.videos_of_day(day), stats=counters["stats"], budget_spent=counters["budget_spent"], top=5)
    free = rep["free"]
    for name, value, unit in (("FreeVideosDay", free["videos"], "Count"), ("PaidVideosDay", rep["paid_videos"], "Count"), ("FreeUsersDay", free["users"], "Count"),
                              ("FreeCreditsDay", rep["credits"]["free"], "Count"), ("FreeCostTrackedUsdDay", free["tracked_usd"], "None"),
                              ("FreeCostEstimatedUsdDay", free["estimated_usd"], "None"), ("FreeCostPerUserUsdDay", free["estimated_usd_per_user"], "None"),
                              ("ClaimsGrantedDay", rep["claims"]["granted"], "Count"), ("ClaimsRefusedDay", sum(rep["claims"]["refused"].values()), "Count")):
        free_grants.emit(name, value, unit)
    rep["top_free_users"] = [{**u, "user": str(u["user"])[:8]} for u in rep["top_free_users"]]   # the log keeps a short prefix only
    logger.info("PLANS_DAILY %s", json.dumps(rep, default=str))
    return rep
