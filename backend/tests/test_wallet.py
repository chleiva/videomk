import json
import threading

import pytest

from common import wallet

DAY = 86400


@pytest.fixture(autouse=True)
def two_daily_credits(monkeypatch):
    """The scenarios below are written for 2 daily credits so spending across buckets is visible; the product default is locked separately."""
    monkeypatch.setenv("WALLET_DAILY_CREDITS", "2")
T0 = 1_800_000_000.0  # a fixed instant: 2027-01-15 08:00:00 UTC


def kinds(user, now, tz=None):
    return {b["kind"]: b["remaining"] for b in wallet.balance(user, now=now, tz=tz)["buckets"]}


def test_credits_are_started_minutes():
    f = wallet.credits_for_minutes
    assert [f(x) for x in (0.1, 0.5, 1, 1.01, 2, 2.5, 3, 12, 99)] == [1, 1, 1, 2, 2, 3, 3, 12, 12]


def test_a_new_user_gets_five_welcome_credits_once_and_daily_credits_start_the_next_day(aws):
    assert kinds("u", T0) == {"signup": 5}
    assert kinds("u", T0 + 3600) == {"signup": 5}                      # no daily credits on day one, and no second welcome
    nxt = T0 + DAY                                                     # next UTC day
    assert kinds("u", nxt) == {"daily": 2, "signup": 5}
    assert kinds("u", nxt + 60) == {"daily": 2, "signup": 5}           # once per day


def test_daily_credits_expire_at_the_end_of_the_local_day_and_are_not_carried_over(aws):
    wallet.balance("u", now=T0)                                         # Jan 15 08:00 UTC
    day2 = T0 + DAY                                                     # Jan 16 08:00 UTC: the first daily credits
    assert kinds("u", day2) == {"daily": 2, "signup": 5}
    midnight = T0 + DAY + 16 * 3600                                     # Jan 17 00:00 UTC
    assert kinds("u", midnight - 60)["daily"] == 2                      # still valid a minute before the day ends
    after = kinds("u", midnight + 60)
    assert after["daily"] == 2 and after["signup"] == 5                 # yesterday's expired and today's fresh 2 appeared: 2, not 4
    assert wallet.balance("u", now=midnight + 60)["balance"] == 7


def test_the_local_day_uses_the_users_timezone_and_timezone_hopping_cannot_earn_extra_days(aws):
    LA, NZ = "America/Los_Angeles", "Pacific/Auckland"
    wallet.balance("u", now=T0, tz=LA)                                  # Jan 15 00:00 in LA
    assert "daily" not in kinds("u", T0 + 3600, tz=LA)
    d2 = T0 + 25 * 3600                                                 # Jan 16 09:00 UTC = Jan 16 01:00 in LA
    assert kinds("u", d2, tz=LA)["daily"] == 2
    got = wallet.balance("u", now=d2, tz=LA)["balance"]
    # claiming "tomorrow" by switching to Auckland (Jan 17 there) within the same UTC day is refused...
    assert wallet.balance("u", now=d2 + 5 * 3600, tz=NZ)["balance"] == got
    # ...and bouncing between zones all day earns nothing more
    for h in (6, 8, 10, 12, 14):
        assert wallet.balance("u", now=d2 + h * 3600, tz=NZ if h % 4 == 2 else LA)["balance"] == got
    assert wallet.local_day(T0, "Not/AZone")[0] == "2027-01-15"        # an unknown timezone is UTC, never an error


def test_a_night_owl_still_gets_the_next_days_credits(aws):
    LA = "America/Los_Angeles"
    wallet.balance("u", now=T0, tz=LA)
    late = T0 + 47 * 3600 + 50 * 60                                     # Jan 16, 23:50 in LA (07:50 UTC Jan 17)
    assert kinds("u", late, tz=LA)["daily"] == 2                        # claimed with ten minutes left of that day
    assert wallet.balance("u", now=late + 20 * 60, tz=LA)["balance"] == 5  # 00:10: a new local day, but the same UTC day: not yet
    assert kinds("u", late + 17 * 3600, tz=LA)["daily"] == 2            # the next UTC day arrives: today's credits are there


def test_spending_takes_the_soonest_expiring_credits_first_then_paid_last(aws):
    wallet.balance("u", now=T0)
    now = T0 + DAY
    wallet.grant_paid("u", 10, "txn-1", now=now)
    assert kinds("u", now) == {"daily": 2, "signup": 5, "paid": 10}
    taken = wallet.charge("u", 3, now=now)
    assert [x["n"] for x in taken] == [2, 1] and "daily" in taken[0]["sk"] and "signup" in taken[1]["sk"]
    assert kinds("u", now) == {"signup": 4, "paid": 10}
    wallet.charge("u", 6, now=now)
    assert kinds("u", now) == {"paid": 8}


def test_not_enough_credits_is_refused_and_takes_nothing(aws):
    wallet.balance("u", now=T0)
    with pytest.raises(wallet.InsufficientCredits) as e:
        wallet.charge("u", 6, now=T0)
    assert (e.value.balance, e.value.needed) == (5, 6) and wallet.balance("u", now=T0)["balance"] == 5


def test_expired_credits_cannot_be_spent(aws):
    wallet.balance("u", now=T0)
    later = T0 + 31 * DAY                                               # welcome credits last 30 days
    assert wallet.balance("u", now=later)["balance"] == 2               # only that day's free credits
    with pytest.raises(wallet.InsufficientCredits):
        wallet.charge("u", 3, now=later)


def test_two_simultaneous_requests_can_never_overspend(aws):
    wallet.balance("u", now=T0)
    results = []

    def go():
        try:
            wallet.charge("u", 3, now=T0)
            results.append("ok")
        except wallet.InsufficientCredits:
            results.append("refused")

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 1 and results.count("refused") == 3   # 5 credits fund exactly one 3-credit video
    assert wallet.balance("u", now=T0)["balance"] == 2


def test_refund_returns_credits_to_their_own_bucket_and_makes_good_if_it_expired(aws):
    wallet.balance("u", now=T0)
    taken = wallet.charge("u", 2, now=T0)
    assert wallet.refund("u", taken, now=T0 + 60) == 2 and kinds("u", T0 + 60) == {"signup": 5}
    daily_now = T0 + DAY
    taken = wallet.charge("u", 2, now=daily_now)                        # the 2 daily credits
    assert wallet.refund("u", taken, now=daily_now + DAY) == 2          # refunded after that day ended: its bucket is gone
    assert kinds("u", daily_now + DAY)["refund"] == 2                   # so a 24-hour make-good appears instead


def test_a_failed_video_is_refunded_exactly_once(aws, monkeypatch):
    wallet.balance("u", now=T0)
    taken = wallet.charge("u", 3, now=T0)
    aws.Table("Videos").put_item(Item={"video_id": "v1", "user_id": "u", "charge": json.dumps(taken)})
    item = aws.Table("Videos").get_item(Key={"video_id": "v1"})["Item"]
    assert wallet.refund_video(item) == 3
    assert wallet.refund_video(item) == 0                               # a late duplicate (retry, double notification) gives nothing back
    assert wallet.balance("u", now=T0)["balance"] == 5
    assert wallet.refund_video({"video_id": "v2", "user_id": "u"}) == 0  # nothing was charged


def test_store_purchases_are_granted_once_per_transaction(aws):
    assert wallet.grant_paid("u", 20, "apple-txn-100", now=T0) is True
    assert wallet.grant_paid("u", 20, "apple-txn-100", now=T0) is False  # the store notifying twice never double-credits
    assert wallet.grant_paid("u", 45, "apple-txn-101", now=T0) is True
    assert kinds("u", T0)["paid"] == 65
    assert wallet.balance("u", now=T0 + 400 * DAY)["balance"] >= 65     # paid credits never expire


def test_product_defaults_are_5_welcome_credits_and_1_free_credit_a_day(aws, monkeypatch):
    monkeypatch.delenv("WALLET_DAILY_CREDITS", raising=False)
    monkeypatch.delenv("WALLET_SIGNUP_CREDITS", raising=False)
    r = wallet.rules()
    assert (r["signup"], r["daily"], r["signup_valid_days"], r["credit_unit_seconds"], r["max_minutes"]) == (5, 1, 30, 60, 12)
    assert kinds("fresh", T0) == {"signup": 5} and kinds("fresh", T0 + DAY) == {"daily": 1, "signup": 5}


def test_rules_come_from_server_config(aws, monkeypatch):
    monkeypatch.setenv("WALLET_SIGNUP_CREDITS", "3")
    monkeypatch.setenv("WALLET_DAILY_CREDITS", "1")
    assert kinds("a", T0) == {"signup": 3}
    assert kinds("a", T0 + DAY) == {"daily": 1, "signup": 3}
