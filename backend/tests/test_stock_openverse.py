"""Openverse really gets its turn before Unsplash (round 2, item 8; docs/LIBRARY_ON_DEMAND.md part E). Found against the live API on 2026-11-27:
its thumbnail endpoint answers 424 for every Wikimedia Commons picture, its firewall answers some search words with 403 whatever is asked three times, and only six
candidates were kept before anyone knew whether they could be shown. No network here: the HTTP layer, the token endpoint and the reviewer's model are stand-ins."""
import io
import json
import urllib.parse

import pytest
from PIL import Image

from engine import stock
from engine.netsafe import FetchError


def _jpeg(size=(1920, 1080)):
    b = io.BytesIO()
    Image.new("RGB", size, (120, 150, 180)).save(b, "JPEG")
    return b.getvalue()


JPEG = _jpeg()
COMMONS = "https://upload.wikimedia.org/wikipedia/commons/a/af/Solar_panels_on_a_roof_%28123%29.jpg"


def _result(i, source="wordpress", url=None, width=4000, height=2250, lic="cc0"):
    return {"id": f"id{i}", "source": source, "license": lic, "license_version": "1.0", "width": width, "height": height, "title": f"photo {i}", "creator": f"Bob {i}",
            "url": url or f"https://pd.w.org/photo{i}.jpg", "thumbnail": f"https://api.openverse.org/v1/images/id{i}/thumb/", "foreign_landing_url": f"https://example.org/{i}", "attribution": f"by Bob {i}"}


def _search(results, log=None, refuse=None):
    """A stand-in for the JSON fetch of the search endpoint. `refuse(query)` -> an HTTP status to answer with."""
    def fetch(url, headers=None):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if log is not None:
            log.append({"q": q["q"][0], "page_size": q["page_size"][0], "headers": dict(headers or {})})
        st = refuse(q["q"][0], headers or {}) if refuse else 0
        if st:
            raise FetchError(f"fetch failed: HTTPError {st}", status=st)
        return {"results": list(results)}
    return fetch


@pytest.fixture(autouse=True)
def _clean():
    stock._token.clear()
    stock._absent.clear()
    yield
    stock._token.clear()
    stock._absent.clear()


# ----------------------------------------------------------------------------- cause 1: thumbnails of Wikimedia pictures
def test_a_wikimedia_picture_is_shown_and_fetched_from_wikimedias_own_standard_renderings():
    log = []
    cands = stock.openverse_search("solar panels", _search([_result(0, "wikimedia", COMMONS + "?utm_source=commons.wikimedia.org&utm_content=original", 5184, 3456), _result(1)], log))
    wm, other = cands
    base = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Solar_panels_on_a_roof_%28123%29.jpg/"
    assert wm["thumb_url"] == base + "500px-Solar_panels_on_a_roof_%28123%29.jpg"                    # not Openverse's /thumb/ of it, which answers 424
    assert wm["full_url"] == base + "1920px-Solar_panels_on_a_roof_%28123%29.jpg" and wm["full_alt"] == COMMONS      # "prefer thumbnails to downloading of originals"; the original as the way back, without the tracking query
    assert other["thumb_url"] == "https://api.openverse.org/v1/images/id1/thumb/" and other["full_url"] == "https://pd.w.org/photo1.jpg" and "full_alt" not in other   # every other source exactly as before
    assert log[0]["page_size"] == "20" and log[0]["headers"] == {}                                    # the largest anonymous page; no credentials invented
    assert stock.is_wikimedia(wm) and not stock.is_wikimedia(other)


def test_only_standard_widths_of_real_wikimedia_jpeg_and_png_files_and_never_larger_than_the_original():
    assert stock.wikimedia_step(COMMONS, 500, 4000).endswith("/500px-Solar_panels_on_a_roof_%28123%29.jpg")
    assert stock.wikimedia_step(COMMONS, 1920, 1920) is None and stock.wikimedia_step(COMMONS, 3840, 2812) is None      # not wider than that: the original is used
    assert stock.wikimedia_step("https://upload.wikimedia.org/wikipedia/commons/a/af/Old_map.tif", 500, 4000) is None    # other file types keep what they had
    assert stock.wikimedia_step("https://pd.w.org/photo.jpg", 500, 4000) is None and stock.wikimedia_step("", 500, 4000) is None
    long = "https://upload.wikimedia.org/wikipedia/commons/a/af/" + "x" * 170 + ".jpg"
    assert stock.wikimedia_step(long, 500, 4000).endswith("/500px-thumbnail.jpg")
    narrow = stock.openverse_search("q", _search([_result(0, "wikimedia", COMMONS, 1800, 1200)]))[0]
    assert narrow["full_url"] == COMMONS and narrow["thumb_url"].endswith("/500px-Solar_panels_on_a_roof_%28123%29.jpg")


def test_a_4k_video_asks_wikimedia_for_its_3840_rendering(monkeypatch):
    monkeypatch.setattr(stock, "unsplash_search", lambda q, key, fetch, **kw: [])
    fetch = _search([_result(0, "wikimedia", COMMONS, 5184, 3456)])
    assert "/1920px-" in stock.gather("q", fetch=fetch)[0]["full_url"]
    big = stock.gather("q", fetch=fetch, big=True)[0]
    assert "/3840px-" in big["full_url"] and "full_url_4k" not in big and stock.public_meta(big)["full_alt"] == COMMONS


# ----------------------------------------------------------------------------- cause 3: six candidates were kept before anyone knew whether they could be shown
def _world(monkeypatch, openverse, dead=()):
    """The real reviewer path with a stand-in model that always chooses the first picture it is shown. -> the list of thumbnails the model was shown per review."""
    seen = []
    monkeypatch.setattr(stock, "openverse_search", lambda q, fetch, **kw: [dict(c) for c in openverse])
    monkeypatch.setattr(stock, "unsplash_search", lambda q, key, fetch, **kw: [{"provider": "unsplash", "id": f"u{i}", "thumb_url": f"https://t/u{i}", "full_url": f"https://f/u{i}", "width": 4000, "height": 2250,
                                                                                 "creator": "Ana", "license": "Unsplash License", "download_location": ""} for i in range(6)])
    monkeypatch.setattr(stock, "track_download", lambda c, key, fetch=None: True)

    def fetch_bytes(url, **kw):
        if url in dead:
            raise FetchError("fetch failed: HTTPError 424", status=424)
        return JPEG

    def complete(system, user, images=None, **kw):
        seen.append(len(images))
        return json.dumps({"choice": 1, "scores": [8] * len(images), "reason": "fits"}), {"cost_usd": 0.0005}
    from engine import llm
    monkeypatch.setattr(llm, "complete", complete)
    return seen, lambda: stock.scout_reviewed("solar panels on a roof", "the sun makes power", "panels", unsplash_key="k", fetch_bytes_fn=fetch_bytes)


def _cand(i, host="t"):
    return {"provider": "openverse", "id": f"o{i}", "thumb_url": f"https://{host}/o{i}", "full_url": f"https://f/o{i}", "width": 3000, "height": 2000, "creator": f"Bob {i}", "license": "CC0 1.0"}


def test_candidates_that_cannot_be_shown_do_not_use_up_the_reviewers_six_places(monkeypatch):
    openverse = [_cand(i) for i in range(12)]
    seen, run = _world(monkeypatch, openverse, dead={f"https://t/o{i}" for i in range(6)})       # the first six thumbnails all fail (what QA logged as "no thumbnails could be loaded")
    out = run()
    assert out["chosen"] == "openverse:o6" and out["credit"] == "Photo: Bob 6 (CC0 1.0)" and out["review"]["source"] == "llm"     # it was Unsplash before
    assert seen == [6]                                                                             # one review, of the six that loaded; Unsplash never looked at


def test_the_reviewer_is_never_shown_more_than_six_and_a_dead_source_still_falls_back_to_unsplash(monkeypatch):
    seen, run = _world(monkeypatch, [_cand(i) for i in range(12)])
    assert run()["chosen"] == "openverse:o0" and seen == [6]
    seen2, run2 = _world(monkeypatch, [_cand(i) for i in range(12)], dead={f"https://t/o{i}" for i in range(12)})
    out = run2()
    assert out["chosen"] == "unsplash:u0" and seen2 == [6]                                         # nothing of the other sources could be shown: the last resort, reviewed


def test_no_more_than_three_wikimedia_pictures_among_the_six_when_other_sources_have_some(monkeypatch):
    monkeypatch.setattr(stock, "unsplash_search", lambda q, key, fetch, **kw: [])
    res = [_result(i, "wikimedia", f"https://upload.wikimedia.org/wikipedia/commons/a/a{i}/W{i}.jpg") for i in range(8)] + [_result(10 + i) for i in range(4)]
    got = stock.gather("q", fetch=_search(res))
    assert len(got) == 12 and [stock.is_wikimedia(c) for c in got[:7]] == [True, True, True, False, False, False, False]      # relevance order, but the fourth Wikimedia picture waits behind the others
    only = stock.gather("q", fetch=_search(res[:8]))
    assert [c["id"] for c in only] == [f"id{i}" for i in range(8)]                                 # nothing else to show: Wikimedia's own order


# ----------------------------------------------------------------------------- cause 2: the firewall refuses some search words
def test_a_search_the_firewall_refuses_is_asked_again_with_one_word_less_never_the_same_way_twice():
    log = []
    fetch = _search([_result(0)], log, refuse=lambda q, h: 403 if "outdoors" in q else 0)
    got = stock.openverse_search("toddler walking outdoors smiling", fetch)
    assert [c["id"] for c in got] == ["id0"]
    assert [x["q"] for x in log] == ["toddler walking outdoors smiling", "toddler walking outdoors", "toddler walking smiling"]     # it was the same question three times, and no photo
    log.clear()
    with pytest.raises(FetchError):
        stock.openverse_search("outdoors", _search([], log, refuse=lambda q, h: 403))
    assert len(log) == 1                                                                           # nothing to leave out: one request, not three
    log.clear()
    with pytest.raises(FetchError):
        stock.openverse_search("a b c d e f", _search([], log, refuse=lambda q, h: 403))
    assert len(log) == 4 and len({x["q"] for x in log}) == 4                                       # at most three other wordings


def test_a_server_error_is_still_tried_three_times_and_then_given_up():
    log = []
    with pytest.raises(FetchError):
        stock.openverse_search("sea waves", _search([], log, refuse=lambda q, h: 504))
    assert [x["q"] for x in log] == ["sea waves"] * 3


# ----------------------------------------------------------------------------- a registered application, when the owner has one
def test_a_registered_application_is_used_when_its_credentials_are_given(monkeypatch):
    posts, log, clock = [], [], [1000.0]

    def post(url, fields, timeout=15):
        posts.append((url, dict(fields)))
        return {"access_token": "tok-1", "token_type": "Bearer", "expires_in": 3600, "scope": "read"}
    monkeypatch.setattr(stock, "_post_form", post)
    monkeypatch.setattr(stock.time, "time", lambda: clock[0])
    assert stock.openverse_auth("", post=post) == {} and stock.openverse_auth("no-colon", post=post) == {} and posts == []         # no credentials: anonymous, nothing asked
    fetch = _search([_result(0)], log)
    stock.openverse_search("sea", fetch, key="my-id:my-secret")
    stock.openverse_search("sky", fetch, key="my-id:my-secret")
    assert posts == [("https://api.openverse.org/v1/auth_tokens/token/", {"client_id": "my-id", "client_secret": "my-secret", "grant_type": "client_credentials"})]   # ONE token for both searches
    assert [x["headers"] for x in log] == [{"Authorization": "Bearer tok-1"}] * 2
    cands = stock.gather("sea", unsplash_key="", fetch=fetch, openverse_key="my-id:my-secret")
    assert "tok-1" not in json.dumps(cands) and "my-secret" not in json.dumps(cands)                 # the token never travels with a candidate (thumbnails and pictures are fetched without it)
    clock[0] += 3600                                                                                 # past its life: a new one
    stock.openverse_search("sun", fetch, key="my-id:my-secret")
    assert len(posts) == 2


def test_a_refused_or_broken_credential_never_costs_the_photo(monkeypatch):
    calls, log = [], []

    def post(url, fields, timeout=15):
        calls.append(1)
        raise OSError("down")
    monkeypatch.setattr(stock, "_post_form", post)
    fetch = _search([_result(0)], log)
    assert len(stock.openverse_search("sea", fetch, key="id:secret")) == 1 and len(stock.openverse_search("sky", fetch, key="id:secret")) == 1
    assert calls == [1] and [x["headers"] for x in log] == [{}, {}]                                  # anonymous, and the failure is remembered: one token request, not one per search
    stock._token.clear()
    log.clear()
    monkeypatch.setattr(stock, "_post_form", lambda url, fields, timeout=15: {"access_token": "old", "expires_in": 3600})
    got = stock.openverse_search("sea", _search([_result(0)], log, refuse=lambda q, h: 401 if h.get("Authorization") else 0), key="id:secret")
    assert len(got) == 1 and [x["headers"] for x in log] == [{"Authorization": "Bearer old"}, {}]    # the API refused the token: the same search once more without it


def test_an_optional_credential_that_is_not_there_is_not_asked_for_at_every_photo():
    asked, clock = [], [0.0]

    def get(name, quiet=False):
        asked.append((name, quiet))
        return ""
    for _ in range(5):
        assert stock.optional_secret(stock.OPENVERSE_KEY_PARAM, get, now=lambda: clock[0]) == ""
    assert asked == [("/videomk/openverse_api_key", True)]
    clock[0] = 901.0
    assert stock.optional_secret(stock.OPENVERSE_KEY_PARAM, lambda name, quiet=False: "id:secret", now=lambda: clock[0]) == "id:secret"


# ----------------------------------------------------------------------------- the picture itself
def test_the_picture_waits_once_when_the_host_says_too_many_requests_and_falls_back_to_the_original():
    c = {"provider": "openverse", "id": "w", "full_url": "https://upload.wikimedia.org/x/1920px-A.jpg", "full_alt": "https://upload.wikimedia.org/x/A.jpg"}
    waits, asked = [], []

    def busy_once(url, **kw):
        asked.append(url)
        if len(asked) == 1:
            raise FetchError("fetch failed: HTTPError 429", status=429, retry_after=11.0)
        return JPEG
    assert stock.fetch_full(c, busy_once, sleep=waits.append) == JPEG and waits == [11.0] and asked == [c["full_url"]] * 2

    asked.clear()
    waits.clear()

    def no_rendering(url, **kw):
        asked.append(url)
        if "1920px" in url:
            raise FetchError("fetch failed: HTTPError 400", status=400)
        return JPEG
    assert stock.fetch_full(c, no_rendering, sleep=waits.append) == JPEG and asked == [c["full_url"], c["full_alt"]] and waits == []

    def blocked(url, **kw):
        raise FetchError("fetch failed: HTTPError 429", status=429, retry_after=600.0)
    with pytest.raises(FetchError):
        stock.fetch_full(c, blocked, sleep=waits.append)
    assert waits == []                                                                               # a long wait is not served: the next candidate or source is used
    assert stock.fetch_full({"full_url": "https://f/u1"}, lambda url, **kw: JPEG) == JPEG            # every other candidate: one request, as always
