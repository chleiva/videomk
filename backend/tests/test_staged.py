import json
import re
import threading

import pytest

from engine import director, plan as plan_mod, staged


def outline_json(n, minutes, **extra):
    return json.dumps({"legit": True, "title": "All About Paris", "description": "A tour.", "mood": "bright", "theme": "sunrise", "voices": {"narrator": "Ruth"},
                       "music": {"track": "acoustic-warm"},
                       "sections": [{"title": f"Part {i + 1}", "goal": f"goal {i + 1}", "key_points": [f"point {i + 1}a", f"point {i + 1}b"], "queries": [f"paris part {i + 1}"], "minutes": minutes / n,
                                     **({"music": {"track": "soft-piano"}} if i == 2 else {})} for i in range(n)], **extra})


def section_json(idx, words_total, n_beats, *, silent=False):
    each = max(1, words_total // n_beats)
    beats = [{"narration": f"Section {idx} beat {j} " + " ".join(["word"] * each), "scene": {"type": "title", "props": {"title": f"S{idx}B{j}"}}} for j in range(n_beats)]
    if silent:
        beats[2] = {"narration": "", "hold": 4, "scene": {"type": "image", "props": {"image_query": "paris skyline", "word": "Paris"}}}
    return json.dumps({"legit": True, "beats": beats, "sources_used": [f"Source {idx}"]})


class FakeModel:
    """Answers the outline call and each section call; records what it was asked, thread-safely."""

    def __init__(self, minutes, n, words_for=None):
        self.minutes, self.n, self.calls, self.lock = minutes, n, [], threading.Lock()
        self.words_for = words_for or (lambda idx, target: (target, 6))

    def __call__(self, system, user):
        with self.lock:
            self.calls.append((system[:40], user))
        if "head writer" in system:
            return outline_json(self.n, self.minutes)
        k = int(re.search(r"section (\d+) of", user).group(1))
        target = int(re.search(r"\(about (\d+)\)", user).group(1))
        words, beats = self.words_for(k, target)
        return section_json(k, words, beats, silent=(k == 2))


def run(minutes=5.0, n=None, research=None, words_for=None, **kw):
    n = n or staged.section_count(minutes)
    model = FakeModel(minutes, n, words_for)
    plan, warns, info = staged.generate("All about Paris", "background notes", minutes, model, research=research, **kw)
    return model, plan, warns, info


def test_long_videos_are_staged_and_short_ones_or_photo_ones_are_not():
    assert staged.is_staged(5) and staged.is_staged(4.0) and not staged.is_staged(3) and not staged.is_staged(5, n_photos=3)
    assert [staged.section_count(m) for m in (4, 5, 8, 12, 30)] == [3, 3, 5, 8, 8]


def test_the_outline_is_scaled_to_the_length_asked_and_made_safe():
    raw = json.loads(outline_json(4, 7.0))
    raw["sections"][0]["minutes"] = 99
    raw["sections"][1]["queries"] = []
    raw["sections"][2]["title"] = ""
    out = staged.parse_outline(raw, 5.0, 4)
    assert len(out["sections"]) == 3 and sum(s["minutes"] for s in out["sections"]) == pytest.approx(5.0, abs=0.03)
    assert out["sections"][1]["queries"] == [out["sections"][1]["title"]]                    # a section with no queries searches for its own title
    with pytest.raises(ValueError):
        staged.parse_outline({"sections": [{"title": "only one"}]}, 5.0, 3)
    with pytest.raises(ValueError):
        staged.parse_outline({"sections": "nope"}, 5.0, 3)


def test_a_five_minute_video_is_an_outline_plus_one_call_per_section_and_hits_the_length():
    model, plan, warns, info = run(5.0)
    outline_calls = [c for c in model.calls if "head writer" in c[0]]
    section_calls = [c for c in model.calls if "head writer" not in c[0]]
    assert len(outline_calls) == 1 and len(section_calls) == info["sections"] == 3
    words = plan_mod.spoken_words(plan["beats"])
    assert words >= 0.85 * plan_mod.expected_words(5.0) and not any(w.startswith("length:") for w in warns)
    assert plan["title"] == "All About Paris" and plan["theme"] == "sunrise" and plan["voices"] == {"narrator": "Ruth"}


def test_each_section_is_told_its_role_its_budget_and_what_the_others_cover():
    model, plan, warns, info = run(6.0, n=4)
    users = {int(re.search(r"section (\d+) of", u).group(1)): u for _, u in model.calls if "section" in u and "head writer" not in _}
    assert "OPENS the video" in users[1] and "CLOSES the video" in users[4] and "continues the video" in users[2]
    for k, u in users.items():
        assert f"Part {k}" in u and "THIS ONE" in u and u.count("<- THIS ONE") == 1                  # the outline is shown with this section marked
        assert "hard requirement" in u and "pays per minute" in u and "Key points this section must cover" in u
    assert all("Part 1" in u and "Part 4" in u for u in users.values())                              # every section sees the whole outline


def test_every_section_gets_its_own_research_and_the_sources_are_collected():
    seen, lock = [], threading.Lock()
    def research(sec):
        with lock:
            seen.append((sec["title"], tuple(sec["queries"])))
        return f"NOTES for {sec['title']}", [{"title": f"Source {sec['title'][-1]}", "url": "https://x", "publisher": "p"}]
    model, plan, warns, info = run(5.0, research=research)
    assert sorted(seen) == [("Part 1", ("paris part 1",)), ("Part 2", ("paris part 2",)), ("Part 3", ("paris part 3",))]
    assert len(info["sources"]) == 3
    section_users = [u for s, u in model.calls if "head writer" not in s]
    assert all(f"NOTES for Part {k}" in "\n".join(section_users) for k in (1, 2, 3))
    assert all("background notes" in u for u in section_users)                                          # the general background still accompanies each section's own notes


def test_a_research_failure_in_one_section_does_not_stop_the_video():
    def research(sec):
        if sec["title"] == "Part 2":
            raise RuntimeError("search provider down")
        return "ok notes", []
    model, plan, warns, info = run(5.0, research=research)
    assert plan["beats"] and plan_mod.spoken_words(plan["beats"]) > 300


def test_the_sections_are_joined_in_order_with_chapters_even_though_they_run_in_parallel():
    model, plan, warns, info = run(5.0)
    narr = [b["narration"] for b in plan["beats"] if not b.get("silent")]
    order = [int(re.search(r"Section (\d+)", n).group(1)) for n in narr]
    assert order == sorted(order) and set(order) == {1, 2, 3}
    assert [b["chapter"] for b in plan["beats"] if b.get("chapter")] == ["Part 1", "Part 2", "Part 3"]
    assert plan["beats"][0].get("chapter") == "Part 1"


def test_a_section_that_is_far_too_short_is_repaired_once_with_its_own_numbers():
    state = {"asked": 0}
    def words_for(k, target):
        if k == 2:
            state["asked"] += 1
            return (target // 3, 6) if state["asked"] == 1 else (target, 6)                           # too short the first time, right the second
        return target, 6
    model, plan, warns, info = run(5.0, words_for=words_for)
    sec2 = [u for s, u in model.calls if "head writer" not in s and "section 2 of" in u]
    assert len(sec2) == 2 and "invalid: the section narration totals" in sec2[1] and "needs about" in sec2[1]
    assert not any("section 2" in w for w in warns)
    state["asked"] = -99                                                                                 # never long enough: accepted with a warning, not looped forever
    model, plan, warns, info = run(5.0, words_for=lambda k, t: (t // 3, 6) if k == 2 else (t, 6))
    assert len([u for s, u in model.calls if "section 2 of" in u]) == 2 and any(w.startswith("section 2:") for w in warns) and plan["beats"]


def test_the_whole_video_goes_through_the_usual_rules_silence_images_and_music_changes():
    model, plan, warns, info = run(5.0)
    kinds = [b.get("silent", False) for b in plan["beats"]]
    assert kinds[0] is False and kinds[-1] is False and not any(a and b for a, b in zip(kinds, kinds[1:]))
    assert plan["music"]["track"] == "acoustic-warm" and plan["music"].get("changes") and plan["music"]["changes"][0]["track"] == "soft-piano"
    chapter_index = next(i for i, b in enumerate(plan["beats"]) if b.get("chapter") == "Part 3")
    assert plan["music"]["changes"][0]["beat"] == chapter_index + 1                                      # the change is at the first beat of the section that chose it


def test_a_section_with_unusable_output_fails_with_a_clear_message_after_one_repair():
    def broken(system, user):
        if "head writer" in system:
            return outline_json(3, 5.0)
        return "I cannot do that"
    with pytest.raises(ValueError, match="section .* could not be written"):
        staged.generate("All about Paris", "", 5.0, broken)


def test_an_illegitimate_request_stops_at_the_outline():
    plan, warns, info = staged.generate("how to hurt people", "", 5.0, lambda s, u: json.dumps({"legit": False, "reason": "No."}))
    assert plan == {"legit": False, "reason": "No."} and info["sections"] == 0


# ================================================================= the director chooses the path
class Provider:
    pass


def test_the_director_stages_a_long_video_with_per_section_research_and_keeps_short_ones_in_one_call(monkeypatch):
    from engine import research as research_mod, researcher

    queries = []
    def fake_research_web(brief, *, decision, **k):
        queries.append((brief[:30], tuple(decision.queries)))
        return researcher.Research(notes="web notes", sources=[{"title": f"Web {len(queries)}", "url": "https://w", "publisher": "p"}], searches=2)
    monkeypatch.setattr(researcher, "research_web", fake_research_web)
    monkeypatch.setattr(researcher, "decide", lambda *a, **k: researcher.Decision(mode="encyclopedia", reason="evergreen"))
    monkeypatch.setattr(research_mod, "gather_notes", lambda topic, **k: ("encyclopedia notes", [{"title": "Paris", "url": "https://en.wikipedia.org/wiki/Paris", "publisher": "Wikipedia"}]))
    model = FakeModel(5.0, 3)
    out = director.direct("All about Paris", minutes=5.0, ask_small=lambda s, u, n=120: "en", ask_big=model, language="en", web_provider=Provider(), ask_tools=lambda *a, **k: None)
    assert out["legit"] and out["research"]["staged"]["sections"] == 3 and out["research"]["section_searches"] == 6 and len(queries) == 3
    assert {s["title"] for s in out["plan"]["sources"]} <= {"Source 1", "Source 2", "Source 3", "Web 1", "Web 2", "Web 3", "Paris"}
    short_model = FakeModel(3.0, 3)
    single = []
    def one_call(system, user):
        single.append(user)
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [{"narration": " ".join(["w"] * 30), "scene": {"type": "title", "props": {"title": "x"}}} for _ in range(14)]})
    out3 = director.direct("All about Paris", minutes=3.0, ask_small=lambda s, u, n=120: "en", ask_big=one_call, language="en")
    assert out3["legit"] and "staged" not in out3["research"] and len(single) == 1
    out_photos = director.direct("My trip", minutes=5.0, ask_small=lambda s, u, n=120: "en", ask_big=one_call, language="en", photos=[{"id": "P1", "caption": "a dog", "orientation": "landscape"}])
    assert "staged" not in out_photos["research"]                                                          # a video built around the user's photos keeps the single call


def test_the_encyclopedia_is_the_fallback_research_for_sections_without_a_search_provider(monkeypatch):
    from engine import research as research_mod
    topics = []
    monkeypatch.setattr(research_mod, "gather_notes", lambda topic, **k: (topics.append(topic), ("notes", []))[1])
    model = FakeModel(5.0, 3)
    director.direct("All about Paris", minutes=5.0, ask_small=lambda s, u, n=120: "en", ask_big=model, language="en")
    assert len(topics) == 1 + 3 and any("Part 1" in t for t in topics) and any("Part 3" in t for t in topics)     # the overall background plus one lookup per section
