"""The safety policy does not block ordinary educational things, and still refuses what it must (round 2, item 7; docs/LIBRARY_ON_DEMAND.md part C7).

QA refused a bee smoker as tobacco, a water gun as a weapon, a christmas tree as religion and a Fresnel lens as a named place: one listed WORD decided. The set in
tests/fixtures/media_policy_regression.json holds the clearly safe asks that the free layers (word lists and filters; no model, no network) must let through, and
the unsafe asks that must be refused. Rows marked "model" can only be refused by the model rubric (German and French have no word lists): they were measured with
the real model (the numbers are in the document), not here."""
import json
import os

import pytest

from common import media_policy as mp
from engine import clip_brief, object_ondemand as oo

SET = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "media_policy_regression.json"), encoding="utf-8"))
SAFE, UNSAFE = SET["safe"], SET["unsafe"]


def _board(*names):
    return {"beats": [{"id": "w1", "scene": {"type": "whiteboard", "props": {"items": [{"id": f"i{k}", "write": n, "boxed": True, "zone": "centre"} for k, n in enumerate(names)]}}}]}


def _drawing_name(ask):
    n = " ".join(ask.lower().split())
    return n if oo.NAME_RE.match(n) and len(n.split()) <= 4 and len(oo.object_id(n)) >= 3 else None


def test_the_set_is_as_large_and_as_wide_as_promised():
    assert len(SAFE) >= 80 and len(UNSAFE) >= 60 and len({r["ask"] for r in SAFE + UNSAFE}) == len(SAFE) + len(UNSAFE)
    assert {r["group"] for r in SAFE} >= {"objects", "animals", "science", "jobs", "tools", "food", "weather", "sports", "festive"}
    for lang in ("en", "es"):                                                                   # every one of the 17 categories, in English and in Spanish
        assert {r["category"] for r in UNSAFE if r["lang"] == lang} == set(mp.CODES), lang
    assert sum(1 for r in UNSAFE if r["lang"] in ("de", "fr")) >= 8 and {r["category"] for r in UNSAFE} == set(mp.CODES) and len(mp.CODES) == 17


@pytest.mark.parametrize("ask", [r["ask"] for r in SAFE])
def test_a_clearly_safe_educational_ask_passes_every_free_layer(ask):
    assert mp.text_reason(ask) is None, mp.text_hits(ask)                                        # the policy's word lists
    assert clip_brief.pre_filter(ask) is None                                                    # the picture and footage search: news, brand, identity, proper noun, privacy, the lists
    name = _drawing_name(ask)
    if name:                                                                                     # the drawing name: it is asked for, not silently dropped
        refused = {}
        assert oo.missing(_board(name), 6, refused=refused) == [(oo.object_id(name), name)], refused


@pytest.mark.parametrize("row", [r for r in UNSAFE if r["by"] == "lists"], ids=lambda r: r["ask"])
def test_an_unsafe_ask_is_refused_before_any_model_is_asked(row):
    ask = row["ask"]
    assert clip_brief.pre_filter(ask) is not None
    name = _drawing_name(ask) if row.get("path") != "search" else None                             # a search wording keeps its capitals; a drawing name has none
    if name:
        refused = {}
        assert oo.missing(_board(name), 6, refused=refused) == [] and refused[name]              # and the refusal has a reason to log
    hits = [c for c, _ in mp.text_hits(ask)]
    if hits:                                                                                     # where the word lists speak, the row's category is among what they say
        assert row["category"] in hits, (ask, hits)


def test_the_five_false_refusals_of_qa_are_gone():
    named = {r["ask"]: r["was"] for r in SAFE if r.get("was")}
    assert set(named) == {"bee smoker", "beekeeper", "lighthouse Fresnel lens", "christmas tree", "water gun"}
    for ask in named:
        assert clip_brief.pre_filter(ask) is None and mp.text_reason(ask) is None, ask
    for name in ("bee smoker", "beekeeper", "christmas tree", "water gun"):
        assert oo.missing(_board(name), 6) == [(oo.object_id(name), name)]


@pytest.mark.parametrize("safe, unsafe, category", [
    ("water gun", "water gun fight between soldiers", "war_weapons"), ("bee smoker", "smoker lighting a cigarette", "drugs_alcohol_tobacco"),
    ("christmas tree", "christmas nativity scene", "religion"), ("easter eggs in a basket", "easter procession with a crucifix", "religion"),
    ("queen bee", "the queen waving from a balcony", "real_people"), ("king penguin", "the king of spain", "real_people"),
    ("baby elephant", "baby sleeping in a cot", "children"), ("killer whale", "killer with a knife", "violence"), ("shooting star", "shooting at a school", "violence"),
    ("red blood cells", "blood on the floor", "injury_medical"), ("copper wire wound into a coil", "bleeding wound on an arm", "injury_medical"),
    ("dinosaur skeleton", "human skeleton in a coffin", "frightening"), ("border collie", "border wall with guards", "flags_maps"),
    ("dead leaves", "dead body under a sheet", "tragedy_disaster"), ("praying mantis", "people praying in a mosque", "religion"),
    ("african elephant", "african tribe dancing", "stereotypes"), ("white picket fence", "picket line of strikers", "politics"),
    ("electrical transformers", "transformers movie robot", "brands_ip"), ("Tesla coil", "Tesla car on a road", "brands_ip"),
    ("pistola de agua", "hombre con una pistola", "war_weapons"), ("bomba de agua", "una bomba explotando", "war_weapons"),
    ("aire puro de montaña", "fumador con un puro", "drugs_alcohol_tobacco"), ("abeja reina", "la reina saludando", "real_people"),
    ("árbol de navidad", "belén de navidad con el niño Jesús", "religion"), ("china teacup", "chinese man with a conical hat", "stereotypes"),
])
def test_only_the_whole_benign_phrase_is_cleared_never_the_word(safe, unsafe, category):
    assert mp.text_reason(safe) is None and clip_brief.pre_filter(safe) is None
    assert category in [c for c, _ in mp.text_hits(unsafe)] and clip_brief.pre_filter(unsafe) is not None


def test_a_capital_letter_in_a_term_of_science_is_not_a_name_and_a_real_name_still_is():
    for ok in ("lighthouse Fresnel lens", "a Bunsen burner on a bench", "bacteria in a Petri dish", "the Geiger counter", "a Tesla coil with sparks", "a swinging Newton's cradle",
               "old Diesel engine", "planet Saturn and its rings", "craters on the Moon", "a Bengal tiger in tall grass", "a French press on a table"):
        assert clip_brief.pre_filter(ok) is None, ok
        assert clip_brief.post_filter({"brief": ok.lower() + " in soft morning light", "people": "none", "motion": "slow", "policy": "none", "tags": []}) is None, ok
    for bad, why in (("Eiffel Tower at sunset", "proper noun"), ("market in Oaxaca on a rainy day", "proper noun"), ("Albert Einstein at a blackboard", "personal (first name)"),
                     ("a Tesla car on a road", "brand"), ("a Windows laptop on a desk", "brand"), ("windows laptop on a desk", "brand")):
        assert clip_brief.pre_filter(bad) == why, bad
    assert clip_brief.pre_filter("open windows of an old house") is None                         # a window is not a brand
    assert clip_brief.pre_filter("ocean waves breaking on rocks") is None and clip_brief.pre_filter("breaking news studio") == "news"
    assert mp.cleared("Árbol de Navidad junto a una iglesia") == "thing junto a una iglesia"      # only the phrase; accents gone, capitals of the rest kept


def test_religious_and_other_things_that_stay_refused_whatever_stands_beside_them():
    for ask in ("christmas mass with a priest", "nativity scene", "a church with christmas lights", "an angel on a christmas tree", "easter mass", "santa praying", "crucifix on a wall",
                "toy gun", "gun", "realistic pistol", "smoker", "cigarette smoker", "baby", "baby boy", "queen", "the king", "skeleton", "human skull", "blood", "dead bird on the road",
                "tornado over a town", "flag", "world map"):
        assert clip_brief.pre_filter(ask) is not None, ask


def test_the_models_read_the_same_short_list_of_exceptions_and_the_first_rule_for_everything_else():
    for system in (clip_brief.BRIEF_SYSTEM, clip_brief.IMAGE_BRIEF_SYSTEM, mp.NAMES_SYSTEM):
        assert mp.ALLOWED in system and "a beekeeper" in system and "a bee smoker" in system and "a Fresnel lens" in system and "decorated tree" in system
        assert "For everything else: when you are unsure whether something touches the policy, it does: refuse" in system
    assert "a beekeeper in a veil" in mp.VISION_SYSTEM and "a toy that looks like a real gun IS a weapon" in mp.VISION_SYSTEM            # the check of the finished picture: said about what is SEEN
    assert "For everything else: when you are unsure whether something touches the policy, it does." in mp.VISION_SYSTEM


def test_a_named_landmark_is_never_turned_into_a_generic_drawing():
    """As a drawing name "eiffel tower" has no capital for the free filters to see; the names rubric used to answer "tower at sunset" and a plain tower was drawn."""
    class Model:
        def __call__(self, system, user, **kw):
            assert 'answer "policy": "specific"' in system
            return json.dumps({"names": [{"n": 1, "english": "tower", "policy": "specific"}, {"n": 2, "english": "lighthouse", "policy": "none"}]}), {"cost_usd": 0.0002}
    out, _ = mp.judge_names(["eiffel tower", "lighthouse"], complete=Model())
    assert [(r["ok"], r["english"], r["reason"]) for r in out] == [(False, "", "specific (a named place, person or work)"), (True, "lighthouse", "")]


def test_the_brief_call_leaves_room_for_a_model_that_thinks_before_it_answers():
    seen = {}

    def model(system, user, **kw):
        seen.update(kw)
        return json.dumps({"reusable": True, "policy": "none", "reason": "", "brief": "a firefighter in a helmet seen from behind beside a red engine", "tags": ["fire"], "people": "distant", "motion": "slow"}), {"cost_usd": 0.0003}
    d, _ = clip_brief.generalise("firefighter", "", "n", complete=model)
    assert d["reusable"] is True and seen["max_tokens"] >= 1000          # at 400 one answer in six came back cut, which reads as a refusal


def test_the_models_own_safe_brief_is_not_refused_for_a_word_of_its_phrase_or_its_tags():
    """Measured with the real model: its briefs for "bee smoker" and "dinosaur skeleton" were right and were then refused by the filters on the answer."""
    ok = {"people": "none", "motion": "slow", "policy": "none"}
    assert clip_brief.post_filter({**ok, "brief": "beekeeper's smoker tool resting on a wooden hive box in soft morning light", "tags": ["beekeeping", "tool", "hive", "smoker"]}) is None
    assert clip_brief.post_filter({**ok, "brief": "a metal smoker with bellows resting beside an open beehive in a meadow", "tags": ["apiary"]}) is None           # the wording itself says what the smoker is
    assert clip_brief.post_filter({**ok, "brief": "large dinosaur skeleton display standing in a quiet museum hall under soft light", "tags": ["dinosaur", "skeleton", "museum"]}) is None
    assert clip_brief.post_filter({**ok, "brief": "fossil skeleton of a large dinosaur standing in a quiet museum hall", "tags": ["fossil"]}) is None
    assert clip_brief.post_filter({**ok, "brief": "a smoker resting on a park bench in soft morning light", "tags": []}) == "policy:drugs_alcohol_tobacco"        # no bees: a smoker is a smoker
    assert clip_brief.post_filter({**ok, "brief": "large dinosaur skeleton display standing in a quiet museum hall", "tags": ["skull"]}) == "policy:frightening"   # a tag that the brief does not say is read alone
    assert clip_brief.post_filter({**ok, "brief": "wooden toy on a table in soft morning light", "tags": ["gun"]}) == "policy:war_weapons"
    assert mp.text_reason("chain smoker beside a beehive with a cigarette") == "policy:drugs_alcohol_tobacco"
    tree = {**ok, "brief": "decorated evergreen tree with warm string lights in a quiet living room at dusk"}
    assert clip_brief.post_filter({**tree, "tags": ["christmas", "holiday", "winter"]}) is None and clip_brief.post_filter({**tree, "tags": ["easter", "spring"]}) is None    # a tag that only says the season
    assert clip_brief.post_filter({**tree, "tags": ["christmas", "nativity"]}) == "policy:religion" and clip_brief.post_filter({**tree, "tags": ["church"]}) == "policy:religion"
    assert clip_brief.post_filter({**tree, "tags": ["water", "gun"]}) == "policy:war_weapons"                                                                  # two tags are not a phrase
    assert clip_brief.post_filter({**ok, "brief": "pale full moon ringed by a faint halo of light over a dark quiet landscape at night", "tags": ["moon", "halo"]}) is None
    assert clip_brief.post_filter({**ok, "brief": "a saint with a golden halo painted on an old wooden panel", "tags": []}) == "policy:religion"
