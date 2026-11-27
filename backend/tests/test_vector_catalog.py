"""Cartoon vector scene catalog lookup (common/vector_catalog.py): search by meaning with fake embeddings, aspect filter, best-effort failure, package fetch."""
import base64
import json
import os
import struct

import pytest

from common import vector_catalog as vc


def enc(v):
    return base64.b64encode(struct.pack(f"<{len(v)}e", *v)).decode("ascii")


def make_index(path):
    items = [
        {"id": "pine_forest_valley", "title": "Pine forest", "category": "nature", "mood": "calm", "tags": ["forest"], "topics": "nature", "aspects": ["16:9"], "palette": ["#112233"], "layers": 6, "svg_kb": 700,
         "vi": enc([1.0, 0.0, 0.0, 0.0]), "vt": enc([0.9, 0.1, 0.0, 0.0])},
        {"id": "city_skyline_day", "title": "City", "category": "city", "mood": "modern", "tags": ["city"], "topics": "business", "aspects": ["16:9"], "palette": [], "layers": 6, "svg_kb": 800,
         "vi": enc([0.0, 1.0, 0.0, 0.0]), "vt": enc([0.0, 0.9, 0.1, 0.0])},
        {"id": "tall_forest_trail", "title": "Trail", "category": "nature", "mood": "calm", "tags": ["trail"], "topics": "hiking", "aspects": ["9:16"], "palette": [], "layers": 6, "svg_kb": 900,
         "vi": enc([0.9, 0.0, 0.3, 0.0]), "vt": enc([0.8, 0.0, 0.4, 0.0])},
    ]
    json.dump({"model": "fake", "dim": 4, "items": items}, open(path, "w"))


@pytest.fixture()
def index(tmp_path, monkeypatch):
    p = str(tmp_path / "idx.json")
    make_index(p)
    vc.load_index.cache_clear()
    monkeypatch.setattr(vc, "INDEX_PATH", p)
    yield p
    vc.load_index.cache_clear()


def embed_forest(_):
    return [1.0, 0.05, 0.0, 0.0]


def test_search_ranks_by_cosine_and_filters_aspect(index):
    r = vc.search("a forest", "16:9", 5, embed=embed_forest)
    assert [x["id"] for x in r] == ["pine_forest_valley"]
    assert r[0]["score"] > 0.9 and r[0]["layers"] == 6
    t = vc.search("a forest", "9:16", 5, embed=embed_forest)
    assert [x["id"] for x in t] == ["tall_forest_trail"]


def test_search_threshold_and_limit(index):
    assert vc.search("zzz", "16:9", 5, embed=lambda _: [0.0, 0.0, 0.0, 1.0]) == []
    r = vc.search("x", "16:9", 1, embed=lambda _: [1.0, 1.0, 0.0, 0.0], min_score=0.1)
    assert len(r) == 1


def test_search_never_raises(index):
    def boom(_):
        raise RuntimeError("bedrock down")
    assert vc.search("forest", "16:9", embed=boom) == []
    assert vc.search("", "16:9", embed=embed_forest) == []
    assert vc.search(None, "16:9", embed=embed_forest) == []   # type: ignore[arg-type]


def test_missing_index_is_empty_catalog(tmp_path, monkeypatch):
    vc.load_index.cache_clear()
    assert vc.load_index(str(tmp_path / "nope.json")) == {"dim": 0, "items": []}
    vc.load_index.cache_clear()


def test_float16_roundtrip_is_close(index):
    items = vc.load_index(index)["items"]
    assert items[0]["vi"] == [1.0, 0.0, 0.0, 0.0]
    assert abs(items[0]["vt"][0] - 0.9) < 1e-3


def test_check_id():
    assert vc.check_id("pine_forest_valley") == "pine_forest_valley"
    for bad in ("../x", "Pine", "a b", "", None, 5, "a" * 80):
        with pytest.raises(ValueError):
            vc.check_id(bad)


def test_fetch_package_local_and_bucket(tmp_path, monkeypatch):
    src = tmp_path / "store" / "pine_forest_valley"
    src.mkdir(parents=True)
    (src / "manifest.json").write_text(json.dumps({"layers": [{"file": "0_sky.svg"}, {"file": "1_layer1.svg"}]}))
    (src / "0_sky.svg").write_text("<svg/>")
    (src / "1_layer1.svg").write_text("<svg/>")
    (src / "thumb.jpg").write_bytes(b"x")
    monkeypatch.setenv("VECTOR_CATALOG_DIR", str(tmp_path / "store"))
    out = vc.fetch_package("pine_forest_valley", str(tmp_path / "work"))
    assert sorted(os.listdir(out)) == ["0_sky.svg", "1_layer1.svg", "manifest.json"]
    monkeypatch.delenv("VECTOR_CATALOG_DIR")

    class S3:
        def __init__(self):
            self.keys = []

        def get_object(self, Bucket, Key):
            self.keys.append(Key)
            body = json.dumps({"layers": [{"file": "0_sky.svg"}]}).encode() if Key.endswith("manifest.json") else b"<svg/>"
            return {"Body": type("B", (), {"read": lambda self: body})()}

    s3 = S3()
    out2 = vc.fetch_package("city_skyline_day", str(tmp_path / "work2"), s3=s3, bucket="b")
    assert s3.keys == ["v/city_skyline_day/manifest.json", "v/city_skyline_day/0_sky.svg"]
    assert sorted(os.listdir(out2)) == ["0_sky.svg", "manifest.json"]
    with pytest.raises(ValueError):
        vc.fetch_package("../etc", str(tmp_path / "w3"), s3=s3, bucket="b")
