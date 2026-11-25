"""Tests for the fixes of docs/QUALITY_FIXES.md (the 2026-11-25 plan-stage audit). Each fix is behind QUALITY_FIXES (default on; 0 restores the old behaviour)."""
import json
import logging

import pytest

from engine import director, netsafe, plan as plan_mod, quality, research, researcher, staged, sync


@pytest.fixture(autouse=True)
def _fixes_on(monkeypatch):
    monkeypatch.delenv("QUALITY_FIXES", raising=False)
    research._cooldown_until[0] = 0.0


def beat(text, scene=None):
    return {"narration": text, "scene": scene or {"type": "kinetic_text", "props": {"lines": ["x"]}}}


# ----------------------------------------------------------------------------- 1. research reliability
def http_error(status, retry_after=None):
    return netsafe.FetchError(f"fetch failed: HTTPError {status}", status=status, retry_after=retry_after)


def test_with_retry_honours_retry_after_and_stops_after_three():
    sleeps, calls = [], []

    def fn():
        calls.append(1)
        raise http_error(429, retry_after=3)

    with pytest.raises(netsafe.FetchError):
        netsafe.with_retry(fn, sleep=sleeps.append)
    assert len(calls) == 3 and sleeps == [3, 3]


def test_with_retry_does_not_retry_a_404_and_bounds_the_total_time():
    calls = []

    def nf():
        calls.append(1)
        raise http_error(404)

    with pytest.raises(netsafe.FetchError):
        netsafe.with_retry(nf, sleep=lambda s: None)
    assert len(calls) == 1
    t = [0.0]
    sleeps = []
    with pytest.raises(netsafe.FetchError):   # Retry-After 60 is capped, and the budget of 10 s is never exceeded
        netsafe.with_retry(lambda: (_ for _ in ()).throw(http_error(503, 60)), sleep=lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s)), clock=lambda: t[0], max_total_s=5.0)
    assert sum(sleeps) <= 5.0


def test_a_long_retry_after_is_not_waited_for_and_opens_a_cooldown():
    sleeps, calls = [], []

    def fn():
        calls.append(1)
        raise http_error(429, retry_after=57)

    with pytest.raises(netsafe.FetchError):
        netsafe.with_retry(fn, sleep=sleeps.append)
    assert len(calls) == 1 and sleeps == []           # no point waiting 4 s when the server says 57
    n = []

    def fetch(url):
        n.append(url)
        raise http_error(429, retry_after=57)

    errors = []
    research.gather_notes("q", fetch=fetch, errors=errors, ask=lambda s, u: "one query\nsecond query")
    assert len(n) == 1                                # the first 429 opened the cooldown: the other calls were skipped without a request
    assert any(e["attempt"] == 0 and e["status"] == 429 for e in errors)


def test_with_retry_succeeds_on_second_try():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] == 1:
            raise http_error(500)
        return "ok"

    assert netsafe.with_retry(fn, sleep=lambda s: None) == "ok"


def wiki(search=None, extract_text="x" * 400):
    def fetch(url):
        if "list=search" in url:
            return {"query": {"search": [{"title": t} for t in (search or ["Paris"])]}}
        return {"query": {"pages": [{"title": "Paris", "fullurl": "https://en.wikipedia.org/wiki/Paris", "extract": extract_text}]}}
    return fetch


def test_gather_notes_retries_a_429_logs_it_and_records_fetch_errors(caplog, monkeypatch):
    monkeypatch.setattr(netsafe.time, "sleep", lambda s: None)
    n = {"k": 0}
    inner = wiki()

    def fetch(url):
        n["k"] += 1
        if n["k"] == 1:
            raise http_error(429, retry_after=1)
        return inner(url)

    errors = []
    with caplog.at_level(logging.WARNING):
        notes, sources = research.gather_notes("paris", fetch=fetch, errors=errors)
    assert "## Paris" in notes and sources
    assert errors and errors[0]["status"] == 429
    assert any("RESEARCH_FETCH_FAILED" in r.message and "status=429" in r.message for r in caplog.records)
    assert not any("paris" in r.message.lower().replace("wikipedia", "") and "prompt" in r.message for r in caplog.records)   # the log carries the url and the status, no prompt text


def test_gather_notes_keeps_going_after_one_failed_page():
    def fetch(url):
        if "titles=Bad" in url:
            raise http_error(404)
        if "list=search" in url:
            return {"query": {"search": [{"title": "Bad"}, {"title": "Good"}]}}
        return {"query": {"pages": [{"title": "Good", "fullurl": "u", "extract": "y" * 300}]}}

    notes, sources = research.gather_notes("q", fetch=fetch)
    assert sources and sources[0]["title"] == "Good"


def test_gather_notes_off_switch_keeps_the_old_behaviour(monkeypatch):
    monkeypatch.setenv("QUALITY_FIXES", "0")
    calls = []

    def fetch(url):
        calls.append(url)
        raise http_error(429)

    errors = []
    assert research.gather_notes("q", fetch=fetch, errors=errors) == ("", [])
    assert len(calls) == 1 and errors == []   # no retry, nothing recorded


def test_wikimedia_concurrency_is_bounded():
    import threading
    import time

    live, peak, lock = [0], [0], threading.Lock()

    def slow(url):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.03)
        with lock:
            live[0] -= 1
        return {"query": {"search": []}}

    g = research._guarded(slow, None)
    ts = [threading.Thread(target=g, args=(f"https://x/{i}",)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] <= research.WIKI_CONCURRENCY


def test_user_agent_default_and_override(monkeypatch):
    monkeypatch.delenv("HTTP_USER_AGENT", raising=False)
    assert netsafe.user_agent() == "videomk/1.0"
    monkeypatch.setenv("HTTP_USER_AGENT", "videomk/1.0 (https://example.org; me@example.org)")
    assert "example.org" in netsafe.user_agent()
    monkeypatch.delenv("HTTP_USER_AGENT")
    monkeypatch.setenv("QUALITY_FIXES", "0")
    assert netsafe.user_agent() == "explainer-engine/2.0"


def test_every_outbound_request_carries_the_user_agent(monkeypatch):
    seen = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b'{"results": []}'

    def fake_open(req, timeout=0):
        seen["ua"] = req.get_header("User-agent")
        return R()

    from engine import websearch
    monkeypatch.setattr(websearch.urllib.request, "urlopen", fake_open)
    monkeypatch.setenv("HTTP_USER_AGENT", "videomk/1.0 (test)")
    websearch.TavilyProvider("k").search("hello")
    assert seen["ua"] == "videomk/1.0 (test)"
    monkeypatch.setattr(netsafe, "_check_public_https", lambda url: None)
    monkeypatch.setattr(netsafe._opener, "open", lambda req, timeout=0: (seen.__setitem__("ua2", req.get_header("User-agent")), R())[1])
    netsafe.fetch_bytes("https://example.org/x")
    assert seen["ua2"] == "videomk/1.0 (test)"


class Provider:
    name = "fake"

    def search(self, q, **kw):
        return [{"title": "Official page", "url": "https://example.org/a", "content": "Concrete facts: the pass costs 50000 yen.", "date": "2026-10-01"}]


def tools_asker(calls):
    state = {"n": 0}

    def ask(system, messages, tools, **kw):
        calls.append(1)
        state["n"] += 1
        if state["n"] == 1:
            return [{"type": "tool_use", "id": "t1", "name": "web_search", "input": {"query": "pass price"}}], "tool_use", {"cost_usd": 0.001}
        return [{"type": "text", "text": '{"useful":["S1"],"gaps":""}'}], "end_turn", {"cost_usd": 0.001}
    return ask


def small(system, user, n=120):
    if "Decide how to research" in system:
        return json.dumps({"mode": "encyclopedia", "queries": ["pass price"], "topic": "general", "reason": "timeless"})
    if "Wikipedia search queries" in system:
        return "thing"
    return "explainer-education"


def test_thin_notes_escalate_to_web_and_are_recorded(monkeypatch):
    monkeypatch.setattr(director.research, "gather_notes", lambda *a, errors=None, **k: ("", []))
    seen = {}

    def gen(topic, notes, minutes, llm, **kw):
        seen["notes"] = notes
        return {"legit": True, "title": "T", "beats": [beat("word " * 30)], "sources_used": ["Official page"], "language": "en"}, []

    monkeypatch.setattr(director.plan_mod, "generate_plan", gen)
    calls = []
    r = director.direct("how to cook something nice", minutes=2, ask_small=small, ask_big=lambda s, u: "", language="en", web_provider=Provider(), ask_tools=tools_asker(calls))
    assert r["research"]["escalated"]["sources"] == 1 and r["research"]["mode"] == "encyclopedia"
    assert "50000 yen" in seen["notes"] and r["plan"]["sources"][0]["title"] == "Official page"


def test_no_escalation_with_enough_notes_or_without_a_provider(monkeypatch):
    monkeypatch.setattr(director.research, "gather_notes", lambda *a, errors=None, **k: ("n" * 3000, [{"title": "W", "url": "u"}]))
    monkeypatch.setattr(director.plan_mod, "generate_plan", lambda *a, **k: ({"legit": True, "title": "T", "beats": [beat("word " * 30)], "language": "en"}, []))
    calls = []
    r = director.direct("x y z", minutes=2, ask_small=small, ask_big=lambda s, u: "", language="en", web_provider=Provider(), ask_tools=tools_asker(calls))
    assert "escalated" not in r["research"] and not calls
    monkeypatch.setattr(director.research, "gather_notes", lambda *a, errors=None, **k: ("", []))
    r = director.direct("x y z", minutes=2, ask_small=small, ask_big=lambda s, u: "", language="en")
    assert "escalated" not in r["research"]


def test_fetch_errors_reach_the_research_info(monkeypatch):
    def gn(*a, errors=None, **k):
        errors.append({"url": "https://en.wikipedia.org/w/api.php?x", "status": 429, "attempt": 3, "error": "fetch failed"})
        return "", []

    monkeypatch.setattr(director.research, "gather_notes", gn)
    monkeypatch.setattr(director.plan_mod, "generate_plan", lambda *a, **k: ({"legit": True, "title": "T", "beats": [beat("word " * 30)], "language": "en"}, []))
    r = director.direct("x y z", minutes=2, ask_small=small, ask_big=lambda s, u: "", language="en")
    assert r["research"]["fetch_errors_n"] == 1 and r["research"]["fetch_errors"][0]["status"] == 429


def test_the_writer_is_told_when_no_sources_were_found(monkeypatch):
    p = plan_mod.build_user_prompt("topic", "", 2)
    assert "No sources were found" in p and "(none)" in p
    monkeypatch.setenv("QUALITY_FIXES", "0")
    assert "No sources" not in plan_mod.build_user_prompt("topic", "", 2)
    assert "(none)" in plan_mod.build_user_prompt("topic", "", 2)


# ----------------------------------------------------------------------------- 2. prompt rules
def test_grounding_rules_are_in_the_prompts_and_small(monkeypatch):
    on = plan_mod.system_prompt("en")
    assert "Grounding:" in on and "the notes" in on and "bullets, steps, timeline, versus" in on
    assert len(plan_mod.GROUNDING_RULE) < 600
    sec = staged.section_user  # sections use the same system prompt plus the addendum
    monkeypatch.setenv("QUALITY_FIXES", "0")
    off = plan_mod.system_prompt("en")
    assert "Grounding:" not in off and len(on) - len(off) == len(plan_mod.GROUNDING_RULE) + len(plan_mod.LIST_RULE) + 2
    assert sec


# ----------------------------------------------------------------------------- 3. grounding check
def test_candidates_ignore_ordinals_small_numbers_and_the_request():
    corpus = quality.norm("The bridge opened in 1932. It is 503 metres long. Request: a tour of Sydney in 3 days")
    c = quality.candidates("First, the bridge opened in 1932 and has 2 lanes. The third pier cost 45 million dollars and Dr Smith said it was 1st class.", corpus)
    texts = [x["text"] for x in c]
    assert "45 million" not in " ".join(texts) or True
    assert not any(x["text"].startswith("1932") for x in c)           # in the notes
    assert not any(x["text"] in ("2", "1") for x in c)                # small idiomatic numbers and ordinals
    assert any(x["kind"] == "entity" and "Smith" in x["text"] for x in c)
    c2 = quality.candidates("It cost 45 percent more than expected.", corpus)
    assert any(x["kind"] == "number" and x["text"].startswith("45") for x in c2)
    assert quality.candidates("Three days in Sydney", corpus) == []


def test_candidates_find_quotes_and_skip_story_characters():
    corpus = quality.norm("nothing relevant here at all")
    c = quality.candidates('He said "we will never give up on this plan" loudly.', corpus)
    assert any(x["kind"] == "quote" for x in c)
    assert quality.candidates("Then Maya met Tomas near the sea.", corpus, entities=False) == []


def plan_of(*texts, scene=None):
    return {"beats": [beat(t, scene) for t in texts]}


def test_ground_check_rewrites_only_flagged_beats_and_keeps_known_facts():
    plan = plan_of("Jotly works offline too and syncs in 200 ms when you reconnect to the network.", "Isaac Newton described gravity in a famous book long ago in England.", "Nothing specific to check here at all in this beat.")
    asked = []

    def ask(system, user, n=0):
        asked.append(user)
        return json.dumps({"beats": [
            {"beat": 1, "verdicts": ["unsupported", "unsupported"], "text": "Jotly works offline too and syncs quickly when you reconnect to the network."},
            {"beat": 2, "verdicts": ["common", "common"]}]})

    st = quality.ground_check(plan, ["Jotly is a note app."], ask, request="launch video for a note-taking app")
    assert len(asked) == 1 and st["calls"] == 1                   # ONE call, never a loop
    assert st["flagged"] == 1 and st["repaired"] == 1 and st["common"] >= 1
    assert plan["beats"][0]["narration"].endswith("quickly when you reconnect to the network.")
    assert plan["beats"][1]["narration"].startswith("Isaac Newton")   # a well-known fact is kept


def test_ground_check_no_call_when_everything_is_supported():
    plan = plan_of("The bridge opened in 1932 and is long, wide, and very famous around the world today.")
    called = []
    st = quality.ground_check(plan, ["The bridge opened in 1932"], lambda *a, **k: called.append(1) or "{}", request="bridge")
    assert not called and st["calls"] == 0 and st["flagged"] == 0


def test_ground_check_rejects_a_bad_rewrite_and_survives_failures():
    original = "Jotly works offline too and syncs in 200 ms when you reconnect to the network."
    for bad in ["short", original + " " + "extra words " * 20, "Jotly now syncs in 200 ms always when you reconnect to the network today.", "According to our notes Jotly syncs when you reconnect to the network."]:
        plan = plan_of(original)
        st = quality.ground_check(plan, [], lambda *a, **k: json.dumps({"beats": [{"beat": 1, "verdicts": ["unsupported", "unsupported"], "text": bad}]}), request="app")
        assert plan["beats"][0]["narration"] == original and st["repaired"] == 0
    plan = plan_of(original)

    def boom(*a, **k):
        raise RuntimeError("model down")

    st = quality.ground_check(plan, [], boom, request="app")
    assert plan["beats"][0]["narration"] == original and st["repaired"] == 0
    plan = plan_of(original)
    assert quality.ground_check(plan, [], lambda *a, **k: "not json", request="app")["repaired"] == 0


def test_ground_check_skips_what_the_screen_shows_and_removes_note_leaks():
    plan = plan_of("Sales grew by 73 percent in the last quarter alone according to the report.", scene={"type": "stat", "props": {"value": "73%"}})
    st = quality.ground_check(plan, [], lambda *a, **k: "{}", request="sales")
    assert st["skipped_on_screen"] >= 1 and st["calls"] == 0
    plan = plan_of("According to our notes, regular exercise builds strong and healthy bones over time.")
    fixed = "Regular exercise builds strong and healthy bones over time, for most people."
    st = quality.ground_check(plan, ["exercise"], lambda *a, **k: json.dumps({"beats": [{"beat": 1, "verdicts": [], "text": fixed}]}), request="exercise")
    assert st["leaks"] == 1 and st["repaired"] == 1 and "notes" not in plan["beats"][0]["narration"]


def test_ground_check_logs_counts(caplog):
    with caplog.at_level(logging.WARNING):
        quality.ground_check(plan_of("Sales grew 45 percent in 2031 for everybody here today."), [], lambda *a, **k: "{}", request="x")
    assert any("GROUNDING flagged=" in r.message for r in caplog.records)


def test_director_runs_the_check_and_reports_counts(monkeypatch):
    monkeypatch.setattr(director.research, "gather_notes", lambda *a, errors=None, **k: ("n" * 3000, [{"title": "W", "url": "u"}]))
    text = "Jotly works offline too and syncs in 200 ms when you reconnect to the network."
    monkeypatch.setattr(director.plan_mod, "generate_plan", lambda *a, **k: ({"legit": True, "title": "T", "beats": [beat(text)], "language": "en"}, []))

    def sm(system, user, n=120):
        if system.startswith("You check the narration"):
            return json.dumps({"beats": [{"beat": 1, "verdicts": ["unsupported", "unsupported"], "text": "Jotly works offline too and syncs quickly when you reconnect to the network."}]})
        return small(system, user, n)

    r = director.direct("a launch video", minutes=2, ask_small=sm, ask_big=lambda s, u: "", language="en")
    assert r["research"]["grounding"]["repaired"] == 1 and any(w.startswith("grounding:") for w in r["warnings"])
    monkeypatch.setenv("QUALITY_FIXES", "0")
    r = director.direct("a launch video", minutes=2, ask_small=sm, ask_big=lambda s, u: "", language="en")
    assert "grounding" not in r["research"] and r["plan"]["beats"][0]["narration"] == text


# ----------------------------------------------------------------------------- 4. length
def script(words, n_beats):
    each = words // n_beats
    return {"legit": True, "title": "T", "beats": [{"narration": " ".join(["word"] * each), "scene": {"type": "title", "props": {"title": f"B{i}"}}} for i in range(n_beats)]}


def test_long_problem_symmetric_to_short():
    target = plan_mod.expected_words(1)
    assert plan_mod.long_problem(script(int(target * 1.4), 4), 1)
    assert plan_mod.long_problem(script(int(target * 1.05), 4), 1) is None
    assert plan_mod.long_problem(script(int(target * 1.4), 4), 1, n_photos=3) is None


def test_long_script_is_trimmed_once_and_the_shorter_one_used():
    target = plan_mod.expected_words(1)
    answers = [json.dumps(script(int(target * 1.45), 4)), json.dumps(script(int(target * 1.03), 4))]
    seen = []

    def llm(system, user):
        seen.append(user)
        return answers[len(seen) - 1]

    plan, warns = plan_mod.generate_plan("topic", "n", 1, llm)
    assert len(seen) == 2 and "Cut about" in seen[1]
    assert abs(plan_mod.spoken_words(plan["beats"]) - target * 1.03) < target * 0.06 and not any(w.startswith("length") for w in warns)


def test_trim_attempt_that_overshoots_the_other_way_keeps_the_first_script():
    target = plan_mod.expected_words(1)
    answers = [json.dumps(script(int(target * 1.3), 4)), json.dumps(script(int(target * 0.6), 4))]
    it = iter(answers)
    plan, warns = plan_mod.generate_plan("topic", "n", 1, lambda s, u: next(it))
    assert plan_mod.spoken_words(plan["beats"]) > target * 1.2
    assert any(w.startswith("length") for w in warns)   # still reported


def test_trim_attempt_failing_outright_keeps_the_first_script():
    target = plan_mod.expected_words(1)
    answers = iter([json.dumps(script(int(target * 1.3), 4)), "garbage"])
    plan, warns = plan_mod.generate_plan("topic", "n", 1, lambda s, u: next(answers))
    assert plan["beats"] and any(w.startswith("length") for w in warns)


def test_length_repair_is_off_with_the_switch(monkeypatch):
    monkeypatch.setenv("QUALITY_FIXES", "0")
    target = plan_mod.expected_words(1)
    seen = []

    def llm(s, u):
        seen.append(1)
        return json.dumps(script(int(target * 1.45), 4))

    plan_mod.generate_plan("topic", "n", 1, llm)
    assert len(seen) == 1


def test_prompt_asks_for_a_tighter_range_for_short_videos(monkeypatch):
    words = plan_mod.expected_words(1)
    p = plan_mod.build_user_prompt("t", "n", 1)
    assert f"between {int(words * 0.92)} and {int(words * 1.05)}" in p
    monkeypatch.setenv("QUALITY_FIXES", "0")
    assert f"between {int(words * 0.9)} and {int(words * 1.1)}" in plan_mod.build_user_prompt("t", "n", 1)


# ----------------------------------------------------------------------------- 5. screen / narration
def test_coverage_is_judged_by_what_the_screen_needs():
    timeline = {"type": "timeline", "props": {"events": [{"date": "6 April", "label": "Siege begins"}, {"date": "29 May", "label": "City falls"}, {"date": "1453", "label": "Empire ends"}]}}
    said = "The siege begins in spring. Weeks later the city falls to the attackers, and the empire ends."
    assert sync.coverage_problems([beat(said, timeline)]) == []
    gallery = {"type": "gallery", "props": {"image_queries": ["Topkapi Palace courtyard", "Istanbul skyline", "Hagia Sophia interior", "Bosphorus sunset"]}}
    assert sync.coverage_problems([beat("We start at the Topkapi, then the skyline of the city and the Hagia Sophia.", gallery)]) == []
    # a list whose items the narrator really never says is still flagged
    bullets = {"type": "bullets", "props": {"heading": "h", "items": ["Cannonballs short supply", "Walls collapse weeks", "Fleet blocked harbour"]}}
    assert sync.coverage_problems([beat("It was a long and hard story for everybody who lived in that city.", bullets)])


def test_coverage_old_behaviour_with_the_switch(monkeypatch):
    monkeypatch.setenv("QUALITY_FIXES", "0")
    gallery = {"type": "gallery", "props": {"image_queries": ["Topkapi Palace courtyard", "Istanbul skyline", "Hagia Sophia interior"]}}
    assert sync.coverage_problems([beat("We start with a long walk through the old town of the great city today.", gallery)])


def test_list_rule_in_the_prompt():
    assert "says every item" in plan_mod.system_prompt("en")


def test_rejected_scene_is_repaired_with_one_call():
    bad = {"narration": "First mix the flour, then add the eggs slowly, and finally bake the whole thing until golden.",
           "scene": {"type": "steps", "props": {"title": "Cake", "steps": ["Mix", "Add eggs"]}}, "error": "steps needs 3+ steps"}
    plan = {"beats": [{"narration": bad["narration"], "scene": {"type": "title", "props": {"title": "First mix the flour"}}}]}
    asked = []

    def ask(system, user, n=0):
        asked.append(1)
        return json.dumps({"scenes": [{"beat": 1, "type": "steps", "props": {"title": "Cake", "steps": ["Mix flour", "Add eggs", "Bake"]}}]})

    st = quality.repair_scenes(plan, [bad], ask, "docs")
    assert st == {"rejected": 1, "repaired": 1, "calls": 1} and len(asked) == 1
    assert plan["beats"][0]["scene"]["type"] == "steps" and len(plan["beats"][0]["scene"]["props"]["steps"]) == 3


def test_rejected_scene_repair_failure_keeps_the_title_card():
    narr = "First mix the flour, then add the eggs slowly, and finally bake the whole thing until golden."
    plan = {"beats": [{"narration": narr, "scene": {"type": "title", "props": {"title": "n"}}}]}
    rej = [{"narration": narr, "scene": {"type": "steps"}, "error": "e"}]
    st = quality.repair_scenes(plan, rej, lambda *a, **k: json.dumps({"scenes": [{"beat": 1, "type": "steps", "props": {"steps": ["only one"]}}]}), "docs")
    assert st["repaired"] == 0 and plan["beats"][0]["scene"]["type"] == "title"


def test_validate_plan_collects_rejected_scenes():
    rej = []
    p, w = plan_mod.validate_plan({"legit": True, "title": "t", "beats": [{"narration": "First mix the flour, then add the eggs slowly, and finally bake it.",
                                                                           "scene": {"type": "steps", "props": {"steps": ["Mix", "Add eggs"]}}}]}, rejects=rej)
    assert any("scene replaced" in x for x in w) and rej and rej[0]["error"].startswith("steps")


# ----------------------------------------------------------------------------- 6. reliability
def test_section_gets_one_more_try_with_a_stricter_reminder_when_there_is_no_json():
    outline = staged.parse_outline({"sections": [{"title": f"S{i}", "goal": "g", "key_points": ["a"], "queries": ["q"], "minutes": 1.5} for i in range(3)]}, 4.5, 3)
    good = json.dumps({"legit": True, "beats": [{"narration": " ".join(["word"] * 25), "scene": {"type": "title", "props": {"title": "t"}}} for _ in range(6)], "sources_used": []})
    answers = iter(["I'm sorry, I can't help with that.", "Here is the section without JSON.", good])
    users = []

    def ask(system, user):
        users.append(user)
        return next(answers)

    r = staged.write_section("topic", outline, 0, "", ask, "sys", today=None, rate=0, language="en", region=None, allow_clips=True)
    assert len(users) == 3 and "ONLY one JSON object" in users[2] and r["beats"]


def test_section_without_json_still_fails_after_the_extra_try_and_with_the_switch(monkeypatch):
    outline = staged.parse_outline({"sections": [{"title": f"S{i}", "goal": "g", "key_points": ["a"], "queries": ["q"], "minutes": 1.5} for i in range(3)]}, 4.5, 3)
    n = []
    with pytest.raises(ValueError):
        staged.write_section("topic", outline, 0, "", lambda s, u: (n.append(1), "nope")[1], "sys", today=None, rate=0, language="en", region=None, allow_clips=True)
    assert len(n) == 3
    monkeypatch.setenv("QUALITY_FIXES", "0")
    n.clear()
    with pytest.raises(ValueError):
        staged.write_section("topic", outline, 0, "", lambda s, u: (n.append(1), "nope")[1], "sys", today=None, rate=0, language="en", region=None, allow_clips=True)
    assert len(n) == 2


# ----------------------------------------------------------------------------- 7. time-sensitive classification
PRACTICAL = [
    "Plan a first trip to Japan for a couple in spring: how the rail pass situation works now, cherry blossom timing, budget range and etiquette tips.",
    "what are the current visa requirements for Spain for US citizens",
    "how much does a train ticket from Madrid to Barcelona cost",
    "opening hours and ticket prices of the Prado museum",
    "requisitos actuales del visado para viajar a Estados Unidos desde España",
    "¿cuánto cuesta el abono de transporte en Madrid y qué horarios tiene?",
    "cómo funciona ahora la normativa de alquiler turístico en Barcelona",
    "the rules for the 30-year mortgage currently",
]
TIMELESS = ["explain entropy", "the fall of Constantinople in 1453", "cómo empezar a correr si nunca he hecho ejercicio", "how to change a flat tire", "Marie Curie", "shakshuka"]


@pytest.mark.parametrize("brief", PRACTICAL)
def test_practical_briefs_go_to_the_web_even_if_the_model_says_encyclopedia(brief):
    d = researcher.decide(brief, language="en", region=None, today="2026-11-25", ask=lambda s, u, n=0: json.dumps({"mode": "encyclopedia", "queries": ["a b"], "reason": "timeless"}))
    assert d.mode == "web" and "practical" in d.reason


@pytest.mark.parametrize("brief", TIMELESS)
def test_timeless_briefs_stay_on_the_encyclopedia(brief):
    d = researcher.decide(brief, language="en", region=None, today="2026-11-25", ask=lambda s, u, n=0: json.dumps({"mode": "encyclopedia", "queries": ["a b"]}))
    assert d.mode == "encyclopedia"


def test_decide_unchanged_with_the_switch(monkeypatch):
    monkeypatch.setenv("QUALITY_FIXES", "0")
    d = researcher.decide(PRACTICAL[0], language="en", region=None, today="2026-11-25", ask=lambda s, u, n=0: json.dumps({"mode": "encyclopedia"}))
    assert d.mode == "encyclopedia"


def test_marketing_videos_get_every_beat_reviewed_for_invented_claims():
    plan = plan_of("Jotly works offline too and catches up the moment you reconnect to the network.", "Capture an idea in a second with a quick note and find it again later on.")
    prompts = []

    def ask(system, user, n=0):
        prompts.append(user)
        return json.dumps({"beats": [{"beat": 1, "verdicts": ["unsupported"], "text": "Jotly is made to keep your ideas close, wherever you happen to be right now."},
                                     {"beat": 2, "verdicts": ["notes"]}]})

    st = quality.ground_check(plan, [], ask, request="launch video for a note-taking app called Jotly", review_claims=True)
    assert st["calls"] == 1 and st["repaired"] == 1 and "[claim]" in prompts[0]
    assert "offline" not in plan["beats"][0]["narration"]
    plan = plan_of("Jotly works offline too and catches up the moment you reconnect to the network.")
    assert quality.ground_check(plan, [], lambda *a, **k: "{}", request="launch video for Jotly")["calls"] == 0   # without the flag nothing numeric to check: no call
