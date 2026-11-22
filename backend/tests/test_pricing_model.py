import importlib.util
import os

import pytest

_spec = importlib.util.spec_from_file_location("pricing_model", os.path.join(os.path.dirname(__file__), "..", "scripts", "pricing_model.py"))
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)
P = pm.Params()


def test_target_margin_holds_for_every_pack_and_length_at_mid_cost_and_15pct_fee():
    assert pm.worst_margin(P) >= pm.TARGET, pm.worst_margin(P)


def test_margin_degrades_gracefully_not_catastrophically_in_bad_cases():
    # documented sensitivity: these are the cases to re-check once real `cost_usd` data exists
    assert pm.worst_margin(P, fee=0.30) > 5.5
    assert pm.worst_margin(P, scenario="high") > 4.0


def test_credit_formula_and_pack_discounts_are_sane():
    assert [pm.credits_for(m) for m in (0.5, 1, 1.2, 3, 12)] == [5, 5, 10, 15, 60]   # per *started* minute
    per_credit = [price / credits for price, credits in pm.PACKS]
    assert per_credit == sorted(per_credit, reverse=True)                              # bigger pack never costs more per credit
    assert per_credit[-1] / per_credit[0] > 0.8                                        # discount capped at 20%


def test_free_allowances_have_bounded_worst_case_cost():
    assert pm.WELCOME["videos"] * pm.cogs(pm.WELCOME["max_minutes"], P) < 0.5          # one-off acquisition cost per account
    assert pm.DAILY["videos"] * pm.cogs(pm.DAILY["max_minutes"], P) < 0.10             # per day, worst case
    original_idea = pm.cogs(5, P) + 10 * pm.cogs(1, P)
    assert original_idea > 7 * pm.DAILY["videos"] * pm.cogs(pm.DAILY["max_minutes"], P)  # why the original idea was rejected


def test_every_ai_edit_action_is_priced_at_least_one_credit_and_non_ai_edits_are_free():
    budget = 9.99 * 0.85 / 100 / pm.TARGET
    for name, c in pm.edit_costs(P).items():
        credits = 0 if c["ai"] == 0 else max(1, -(-c["ai"] // budget))
        assert (credits == 0) == (c["ai"] == 0), name
        if credits:
            assert credits * 9.99 / 100 > 7 * c["ai"], name                          # priced above the 7x line


def test_server_config_roundtrips():
    cfg = pm.server_config(P)
    assert cfg["credits_per_started_minute"] == 5 and len(cfg["packs"]) == 3 and cfg["welcome"]["videos"] == 3
