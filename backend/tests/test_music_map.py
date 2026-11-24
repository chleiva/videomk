import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import music_library  # noqa: E402

DOC = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "MUSIC_MAP.md")


def test_every_track_the_map_names_exists_in_the_library_briefs():
    text = open(DOC, encoding="utf-8").read()
    ids = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`", text))
    assert len(ids) >= 30
    missing = sorted(i for i in ids if i not in music_library.SPEC)
    assert not missing, missing


def test_every_row_has_a_first_choice_and_the_library_covers_a_wide_range_of_energy_and_tempo():
    rows = [l for l in open(DOC, encoding="utf-8").read().splitlines() if re.match(r"\|\s*\d+\s*\|", l)]
    assert len(rows) == 20 and all(re.search(r"\|\s*`[a-z0-9-]+`\s*\|", l) for l in rows)
    energies = {b["energy"] for b in music_library.SPEC.values()}
    bpms = [b["bpm"] for b in music_library.SPEC.values()]
    assert energies == {1, 2, 3, 4, 5} and min(bpms) <= 60 and max(bpms) >= 125 and len(music_library.SPEC) >= 30


def test_every_brief_is_complete_and_instrumental_and_ids_are_unique():
    ids = [b[0] for b in music_library.BRIEFS]
    assert len(ids) == len(set(ids))
    for b in music_library.SPEC.values():
        assert b["brief"] and b["description"] and 1 <= b["energy"] <= 5 and 50 <= b["bpm"] <= 140
        assert "vocal" not in b["brief"].lower() or "no vocal" in b["brief"].lower()
