"""Whiteboard drawing search (engine/whiteboard/retrieval.py, scripts/whiteboard_embed.py): lexical scoring in several languages, fusion, fallbacks, the menu, and a guard that
every library drawing has a vector."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.whiteboard import library, retrieval  # noqa: E402

ITEMS = [
    {"id": "windmill", "category": "places", "title": "Windmill", "title_es": "Molino de viento", "synonyms_en": ["wind mill", "sails"], "synonyms_es": ["molino"], "tags": ["wind", "farm"]},
    {"id": "sun", "category": "nature", "title": "Sun", "title_es": "Sol", "synonyms_en": ["sunshine"], "synonyms_es": ["sol"], "tags": ["day", "light"]},
    {"id": "syringe", "category": "health", "title": "Syringe", "title_es": "Jeringa", "synonyms_en": ["vaccine", "injection"], "synonyms_es": ["vacuna", "inyección"], "tags": ["needle"]},
    {"id": "water_drop", "category": "nature", "title": "Water drop", "title_es": "Gota de agua", "synonyms_en": ["droplet"], "synonyms_es": ["gota"], "tags": ["rain", "water"]},
    {"id": "check_mark", "category": "symbols", "title": "Check mark", "title_es": "Marca de verificación", "synonyms_en": ["tick"], "synonyms_es": [], "tags": []},
]


def test_fold_and_stem_are_accent_and_plural_tolerant():
    assert retrieval.fold("Inyección – Café") == "inyeccion cafe"
    assert retrieval.stem("windmills") == retrieval.stem("windmill")
    assert retrieval.stem("molinos") == retrieval.stem("molino")
    assert retrieval.stem("wolken") == retrieval.stem("wolke")
    assert retrieval.tokens("How does the sundial work") == [retrieval.stem("sundial")]      # stop words and short words go


@pytest.mark.parametrize("query,want", [("how do windmills work", "windmill"), ("Explica cómo funciona un molino de viento", "windmill"), ("la vacuna y la inyección", "syringe"),
                                        ("drops of rain, droplets", "water_drop")])
def test_lexical_finds_the_drawing_in_english_and_spanish(query, want):
    ids, info = retrieval.rank(query, "", items=ITEMS, embed=lambda t: (_ for _ in ()).throw(RuntimeError("no model")))
    assert ids[0] == want and info["embedded"] == 0


def test_embedding_adds_what_words_miss():
    vecs = {it["id"]: np.eye(5, dtype=np.float32)[i] for i, it in enumerate(ITEMS)}
    for it in ITEMS:                                     # inline vectors, as the real index has
        import base64

        it["v"] = base64.b64encode(vecs[it["id"]].astype("<f2").tobytes()).decode()
    retrieval._cache.clear()
    q = np.zeros(5, np.float32)
    q[1] = 1.0                                           # the query is "like" the sun, though no word matches
    ids, info = retrieval.rank("das Gestirn am Himmel", "", items=ITEMS, embed=lambda t: q)
    assert ids[0] == "sun" and info["embedded"] >= 1
    for it in ITEMS:
        it.pop("v")
    retrieval._cache.clear()


def test_rank_without_signal_raises_and_menu_falls_back(monkeypatch):
    monkeypatch.setenv("WB_SEARCH", "1")
    retrieval.set_context("zzzz qqqq", "")
    monkeypatch.setattr(retrieval, "select", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    assert retrieval.menu(library.index()["items"]) is None            # the caller then shows the whole list


def test_off_by_default_is_byte_for_byte_the_old_menu(monkeypatch):
    monkeypatch.delenv("WB_SEARCH", raising=False)
    retrieval.set_context("windmill", "")
    assert retrieval.menu(library.index()["items"]) is None


def test_on_menu_is_small_has_no_cut_and_keeps_generics(monkeypatch):
    monkeypatch.setenv("WB_SEARCH", "1")
    monkeypatch.setenv("WB_SEARCH_K", "30")
    monkeypatch.setattr(retrieval, "_sidecar", lambda: {})
    items = library.index()["items"]
    retrieval.set_context("how a windmill works", "A windmill uses its sails to turn the wind into power.")
    monkeypatch.setattr("common.library_search.embed_text", lambda t: (_ for _ in ()).throw(RuntimeError("down")))     # lexical only
    block = wp.Policy(True, "asked").prompt_block("en")
    body = block[block.index("Drawing ids, by group:"):]
    shown = {i for line in body.splitlines()[1:] for i in line.split(":", 1)[1].replace(" ", "").split(",")}
    assert "windmill" in shown or not any(it["id"] == "windmill" for it in items)
    assert len(shown) <= 30 + len(retrieval.GENERICS)
    assert {"check_mark", "person_standing"} <= shown
    assert len(body) < 4000


def test_a_library_past_the_old_cap_is_not_cut_with_search_on(monkeypatch, caplog):
    """The old menu was cut at MAX_MENU_CHARS (silently: the last categories vanished). Search on: the one drawing a video needs is shown, whatever its position."""
    big = [{"id": f"thing_{n:04d}", "category": f"cat{n % 9}", "title": f"Thing {n}", "title_es": "", "synonyms_en": [], "synonyms_es": [], "tags": []} for n in range(1500)]
    big.append({"id": "zeppelin_airship", "category": "transport", "title": "Zeppelin", "title_es": "Zepelin", "synonyms_en": ["airship", "blimp"], "synonyms_es": ["dirigible"], "tags": []})
    monkeypatch.setattr(library, "index", lambda: {"items": big, "min_score": 0.3})
    monkeypatch.setattr(retrieval, "_sidecar", lambda: {})
    retrieval._cache.clear()
    monkeypatch.setattr("common.library_search.embed_text", lambda t: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setenv("WB_SEARCH", "1")
    retrieval.set_context("how does an airship fly", "")
    block = wp.Policy(True, "asked").prompt_block("en")
    assert "zeppelin_airship" in block and len(block) < 12000
    monkeypatch.setenv("WB_SEARCH", "0")
    with caplog.at_level("WARNING"):
        old = wp.Policy(True, "asked").prompt_block("en")
    assert "zeppelin_airship" not in old and "menu cut" in caplog.text        # the old path still cuts, but now says so
    retrieval._cache.clear()


def test_every_library_drawing_has_a_vector():
    """A new drawing without an embedding would silently never be found: run scripts/whiteboard_embed.py fill."""
    import whiteboard_embed

    assert whiteboard_embed.missing() == []


def test_embed_fill_is_idempotent_and_only_embeds_the_missing(monkeypatch, tmp_path):
    import whiteboard_embed

    items = [{"id": "a_thing", "category": "x", "title": "A thing", "title_es": "Una cosa", "synonyms_en": [], "synonyms_es": [], "tags": []}]
    monkeypatch.setattr(library, "index", lambda: {"items": items})
    monkeypatch.setattr(whiteboard_embed, "PATH", str(tmp_path / "e.json"))
    calls = []
    emb = lambda t: calls.append(t) or [0.1] * 8      # noqa: E731
    assert whiteboard_embed.fill(emb) == (1, 1)
    assert whiteboard_embed.fill(emb) == (0, 1) and len(calls) == 1
    assert whiteboard_embed.missing(items, whiteboard_embed.load()) == []
    items[0]["title"] = "Changed"
    assert whiteboard_embed.fill(emb) == (1, 1)
