"""Stock photo sources are ranked so that Unsplash is the last resort (tracker R155, docs/LIBRARY_ON_DEMAND.md A5): its API terms tie an on-frame credit to every
display, the other sources' do not. No network: the two searches, the reviewer and the downloads are stand-ins."""
import io

import pytest
from PIL import Image

from engine import stock
from engine.netsafe import FetchError


def _jpeg():
    b = io.BytesIO()
    Image.new("RGB", (1920, 1080), (120, 150, 180)).save(b, "JPEG")
    return b.getvalue()


JPEG = _jpeg()


def _unsplash(n):
    return [{"provider": "unsplash", "id": f"u{i}", "thumb_url": f"https://t/u{i}", "full_url": f"https://f/u{i}", "width": 4000, "height": 2250, "creator": f"Ana {i}", "creator_url": "",
             "landing_url": "", "license": "Unsplash License", "alt": "", "download_location": f"https://api.unsplash.com/dl/u{i}", "attribution": f"Photo by Ana {i} on Unsplash"} for i in range(n)]


def _openverse(n):
    return [{"provider": "openverse", "id": f"o{i}", "thumb_url": f"https://t/o{i}", "full_url": f"https://f/o{i}", "width": 3000, "height": 2000, "creator": f"Bob {i}", "creator_url": "",
             "landing_url": "", "license": "BY 4.0" if i % 2 else "CC0 1.0", "alt": "", "download_location": "", "attribution": ""} for i in range(n)]


@pytest.fixture
def world(monkeypatch):
    """`w.unsplash` / `w.openverse`: what each search returns. `w.pick(group)`: the reviewer's choice (index or None). `w.shown`: the groups the reviewer was shown.
    `w.broken`: full urls that cannot be downloaded. `w.tracked`: Unsplash download pings."""
    class W:
        unsplash, openverse, shown, broken, tracked = _unsplash(8), _openverse(8), [], set(), []
        pick = staticmethod(lambda group: 0)
    w = W()
    w.shown, w.broken, w.tracked = [], set(), []
    monkeypatch.setattr(stock, "unsplash_search", lambda q, key, fetch, **kw: list(w.unsplash))
    monkeypatch.setattr(stock, "openverse_search", lambda q, fetch, **kw: list(w.openverse))
    monkeypatch.setattr(stock, "track_download", lambda c, key, fetch=None: w.tracked.append(c["id"]) or True)

    def review(group, narration, alt, query, *, fetch_bytes_fn=None):
        w.shown.append([c["id"] for c in group])
        choice = w.pick(group)
        if isinstance(choice, Exception):
            raise choice
        return choice, "because", 0.001, list(range(len(group)))

    def fetch_bytes(url, **kw):
        if url in w.broken:
            raise FetchError("gone")
        return JPEG
    w.run = lambda **kw: stock.scout_reviewed("sea waves", "the sea", "waves", unsplash_key="k", fetch_bytes_fn=fetch_bytes, review=kw.pop("review", review), **kw)
    return w


def test_the_other_sources_come_first_and_unsplash_last(world):
    cands = stock.gather("sea", unsplash_key="k")
    assert [c["id"] for c in cands] == [f"o{i}" for i in range(8)] + [f"u{i}" for i in range(6)]            # up to twelve of the others (the reviewer is shown the first six that load), six of the last resort: it is always still there
    world.openverse = []
    assert [c["provider"] for c in stock.gather("sea", unsplash_key="k")] == ["unsplash"] * 6
    assert stock.is_last_resort({"provider": "unsplash"}) and not stock.is_last_resort({"provider": "openverse"}) and stock.LAST_RESORT == ("unsplash",)


def test_one_source_failing_never_blocks_the_other(world, monkeypatch):
    monkeypatch.setattr(stock, "openverse_search", lambda q, fetch, **kw: (_ for _ in ()).throw(FetchError("504")))
    assert [c["provider"] for c in stock.gather("sea", unsplash_key="k")] == ["unsplash"] * 6
    out = world.run()
    assert out["chosen"] == "unsplash:u0" and out["credit"] == "Photo: Ana 0 / Unsplash"


def test_a_suitable_photo_from_another_source_wins_and_unsplash_is_never_even_looked_at(world):
    world.pick = lambda group: 2
    out = world.run()
    assert out["chosen"] == "openverse:o2" and out["credit"] == "Photo: Bob 2 (CC0 1.0)" and out["entry"]["source"] == "openverse"   # the credit of that source, exactly as before
    assert world.shown == [[f"o{i}" for i in range(8)]] and world.tracked == ["o2"] or world.tracked == []                           # one review, of the other sources only
    assert [c["provider"] for c in out["candidates"]] == ["openverse"] * 8 + ["unsplash"] * 6 and out["review"]["cost_usd"] == pytest.approx(0.001)


def test_unsplash_is_used_only_when_nothing_else_suits_and_its_credit_stays_exactly_as_today(world):
    world.pick = lambda group: None if group[0]["provider"] == "openverse" else 1
    out = world.run()
    assert out["chosen"] == "unsplash:u1" and out["credit"] == "Photo: Ana 1 / Unsplash"                     # the on-frame credit, unchanged
    assert out["entry"]["license"] == "Unsplash License" and out["entry"]["attribution"] == "Photo by Ana 1 on Unsplash"
    assert world.shown == [[f"o{i}" for i in range(8)], [f"u{i}" for i in range(6)]] and world.tracked == ["u1"]   # the download ping Unsplash asks for, once, for the photo used
    assert out["review"] == {"source": "llm", "reason": "because", "cost_usd": pytest.approx(0.002)}          # both reviews are counted


def test_nothing_suitable_anywhere_is_still_rejected_all(world):
    world.pick = lambda group: None
    out = world.run()
    assert out["rejected_all"] is True and out["jpeg"] is None and len(out["candidates"]) == 14 and len(world.shown) == 2


def test_a_single_other_candidate_is_still_reviewed_before_it_displaces_unsplash(world):
    world.openverse = _openverse(1)
    world.pick = lambda group: None if group[0]["provider"] == "openverse" else 0
    assert world.run()["chosen"] == "unsplash:u0" and world.shown[0] == ["o0"]
    world.shown.clear()
    world.pick = lambda group: 0
    assert world.run()["chosen"] == "openverse:o0" and world.shown == [["o0"]]


def test_a_chosen_photo_that_cannot_be_downloaded_falls_to_the_next_group_not_to_an_unchosen_one(world):
    world.broken = {"https://f/o0"}
    out = world.run()
    assert out["chosen"] == "unsplash:u0" and world.shown == [[f"o{i}" for i in range(8)], [f"u{i}" for i in range(6)]]
    world.broken = {"https://f/o0", "https://f/u0"}
    assert world.run()["chosen"] == "unsplash:u1"                                                            # inside the last group: the next candidate, as always


def test_a_failing_reviewer_never_blocks_the_video_and_unreviewed_photos_come_from_the_curated_source(world):
    world.pick = lambda group: RuntimeError("throttled")
    out = world.run()
    assert out["chosen"] == "unsplash:u0" and out["review"]["source"] == "fallback"
    out = world.run(review=None)                                                                             # no reviewer at all: provider order, the other sources first
    assert out["chosen"] == "openverse:o0" and out["review"]["source"] == "first-result"


def test_only_unsplash_or_only_others_behaves_as_before(world):
    world.openverse = []
    world.pick = lambda group: 3
    assert world.run()["chosen"] == "unsplash:u3" and len(world.shown) == 1
    world.unsplash, world.openverse = [], _openverse(1)
    world.shown.clear()
    assert world.run()["chosen"] == "openverse:o0" and world.shown == []                                      # a lone candidate with nothing else to prefer: used as before, no review
    world.unsplash, world.openverse = [], []
    assert world.run() is None
