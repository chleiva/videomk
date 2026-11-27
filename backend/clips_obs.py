"""The alarms of library clips on demand (docs/CLIPS_ON_DEMAND.md section 9), in a stack of their own: `cdk deploy -c stage=qa -c clipsAlarms=1 [-c clipsDayBudgetUsd=10]`.

Two alarms, no action (there is no notification topic yet, as for the plans alarms): a platform budget refused a generation today; the day's spend of paying accounts reached
80 % of the daily budget. The metrics are written by the beat function through its log (namespace videomk/Clips), so this stack needs nothing from the main one.
"""
from aws_cdk import Duration, Stack, aws_cloudwatch as cw
from constructs import Construct

NAMESPACE = "videomk/Clips"


class ClipsObsStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, day_budget_usd: float = 10.0, **kw) -> None:
        super().__init__(scope, cid, **kw)
        cw.Alarm(self, "BudgetStopAlarm", metric=cw.Metric(namespace=NAMESPACE, metric_name="BudgetStop", dimensions_map={"Kind": "paid"}, statistic="Sum", period=Duration.days(1)),
                 threshold=1, evaluation_periods=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description="Library clips on demand: the platform's daily or monthly budget refused a generation today (paying accounts). docs/CLIPS_ON_DEMAND.md. No action attached.")
        cw.Alarm(self, "SpendAlarm", metric=cw.Metric(namespace=NAMESPACE, metric_name="SpendUsd", dimensions_map={"Kind": "paid"}, statistic="Sum", period=Duration.days(1)),
                 threshold=round(0.8 * day_budget_usd, 2), evaluation_periods=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                 treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description=f"Library clips on demand: paying accounts spent 80 % or more of the ${day_budget_usd:g} daily budget today. docs/CLIPS_ON_DEMAND.md. No action attached.")
