from decimal import Decimal

import pytest

from engine import costs
from tests.test_engine_e2e import USER, env  # noqa: F401  (the fixture)


def item(env, vid):
    return env.Table("Videos").get_item(Key={"video_id": vid})["Item"]


def test_each_charge_can_name_what_it_paid_for_and_the_parts_add_up_to_the_total(env):
    env.Table("Videos").put_item(Item={"video_id": "c1", "user_id": USER, "status": "X"})
    costs.add_cost("c1", 0.0280, part="speech")
    costs.add_cost("c1", 0.0100, part="script")
    costs.add_cost("c1", 0.0030, part="stock")
    costs.add_cost("c1", 0.0020, part="stock")
    costs.add_cost("c1", 0.0060)                          # a charge with no name still counts in the total
    it = item(env, "c1")
    assert it["cost_usd"] == Decimal("0.049") and it["c_speech"] == Decimal("0.028") and it["c_script"] == Decimal("0.01") and it["c_stock"] == Decimal("0.005")
    assert "c_research" not in it and "c_photos" not in it
    parts = sum(it[f"c_{p}"] for p in costs.PARTS if f"c_{p}" in it)
    assert parts <= it["cost_usd"] and it["cost_usd"] - parts == Decimal("0.006")      # only the unnamed charge is missing from the breakdown


def test_the_cost_cap_still_applies_when_a_part_is_named_and_a_refused_charge_is_not_recorded(env, monkeypatch):
    env.Table("Videos").put_item(Item={"video_id": "c2", "user_id": USER, "status": "X"})
    monkeypatch.setattr(costs, "MAX_COST_USD", 0.05)
    costs.add_cost("c2", 0.04, part="speech")
    with pytest.raises(costs.CostCapExceeded):
        costs.add_cost("c2", 0.02, part="script")
    it = item(env, "c2")
    assert it["cost_usd"] == Decimal("0.04") and "c_script" not in it               # the refused charge left nothing behind


def test_a_bad_part_name_is_refused_before_anything_is_written(env):
    env.Table("Videos").put_item(Item={"video_id": "c3", "user_id": USER, "status": "X"})
    for bad in ("speech; DROP", "", "Speech", "unknown"):
        with pytest.raises(ValueError):
            costs.add_cost("c3", 0.01, part=bad)
    assert "cost_usd" not in item(env, "c3")
