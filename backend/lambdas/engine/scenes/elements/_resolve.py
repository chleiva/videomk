"""Turns the names the director wrote into places, offline first (Natural Earth), then Wikidata for landmarks and small towns. Never guesses: a name that cannot be
resolved with confidence raises `ResolveError`, and the beat falls back to a title card.

An entity is a small JSON dict:
  {"t": "country", "id": "FRA", "n": "France"}                    a country (polygon from adm0)
  {"t": "admin1",  "id": "USA-3514", "n": "Texas", "c": "USA"}     a state/province (polygon from adm1)
  {"t": "point",   "lon": 2.35, "lat": 48.85, "n": "Paris", "s": "ne"|"wd"|"country"|"admin1"}
  {"t": "frame",   "box": [lon_min, lat_min, lon_max, lat_max], "n": "Europe"}   a named stretch of the world, only used to frame the camera
"""
import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import _geo

Entity = Dict[str, Any]

USER_AGENT = "videomk-map-resolver/1.0 (explainer video generator; place lookup via Wikidata, CC0)"
HTTP_TIMEOUT = 4.0
WD_API = "https://www.wikidata.org/w/api.php"


class ResolveError(ValueError):
    pass


class NotFound(ResolveError):
    pass


class Ambiguous(ResolveError):
    pass


# ----------------------------------------------------------------------------- names
_ABBR = {"st": "saint", "ste": "sainte", "mt": "mount", "ft": "fort", "pt": "port"}


def fold(s: Any) -> str:
    """Lower-case, accent-free, punctuation-free form used to compare names: "Côte d'Ivoire" -> "cote d ivoire", "St. Petersburg" -> "saint petersburg"."""
    s = unicodedata.normalize("NFKD", str(s or "")).replace("ß", "ss").replace("ø", "o").replace("Ø", "o").replace("đ", "d").replace("ł", "l").replace("Ł", "l")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    words = [_ABBR.get(w, w) for w in s.split()]
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


# country aliases by Natural Earth ADM0_A3 (the folded NE names, long names, formal names and translations are indexed automatically)
COUNTRY_ALIASES = {
    "USA": ["usa", "us", "u s", "u s a", "america", "united states", "united states of america", "the states"],
    "GBR": ["uk", "u k", "united kingdom", "great britain", "britain", "gb"],
    "CZE": ["czechia", "czech republic"],
    "CIV": ["ivory coast", "cote d ivoire", "cote divoire"],
    "MMR": ["burma", "myanmar"],
    "SWZ": ["eswatini", "swaziland", "kingdom of eswatini"],
    "NLD": ["netherlands", "holland", "the netherlands"],
    "RUS": ["russia", "russian federation"],
    "KOR": ["south korea", "republic of korea"],
    "PRK": ["north korea", "dprk"],
    "COD": ["dr congo", "drc", "democratic republic of the congo", "congo kinshasa", "dem rep congo"],
    "COG": ["republic of the congo", "congo brazzaville", "congo"],
    "ARE": ["uae", "united arab emirates", "emirates"],
    "MKD": ["north macedonia", "macedonia"],
    "TLS": ["east timor", "timor leste"],
    "CPV": ["cape verde", "cabo verde"],
    "TUR": ["turkey", "turkiye"],
    "VAT": ["vatican", "vatican city", "holy see"],
    "PSE": ["palestine", "state of palestine", "west bank"],
    "TWN": ["taiwan"],
    "LAO": ["laos"],
    "VNM": ["vietnam", "viet nam"],
    "SYR": ["syria"],
    "IRN": ["iran"],
    "BOL": ["bolivia"],
    "VEN": ["venezuela"],
    "TZA": ["tanzania"],
    "MDA": ["moldova"],
    "BRN": ["brunei"],
    "SRB": ["serbia"],
    "BIH": ["bosnia", "bosnia and herzegovina"],
    "GNB": ["guinea bissau"],
    "SSD": ["south sudan"],
    "CAF": ["central african republic"],
    "DOM": ["dominican republic"],
    "FSM": ["micronesia"],
    "SLB": ["solomon islands"],
    "BHS": ["bahamas", "the bahamas"],
    "GMB": ["gambia", "the gambia"],
    "NZL": ["new zealand", "aotearoa"],
    "CHN": ["china", "prc", "peoples republic of china"],
    "HKG": ["hong kong"],
    "MAC": ["macau", "macao"],
    "SAU": ["saudi arabia", "saudi"],
}

# city aliases -> the Natural Earth name (offline)
CITY_ALIASES = {
    "nyc": "New York", "new york city": "New York", "bombay": "Mumbai", "calcutta": "Kolkata", "madras": "Chennai", "peking": "Beijing", "saigon": "Ho Chi Minh City",
    "rangoon": "Yangon", "kiev": "Kyiv", "washington dc": "Washington, D.C.", "washington d c": "Washington, D.C.", "dc": "Washington, D.C.", "mexico city": "Mexico City",
    "bangkok": "Bangkok", "st petersburg": "Saint Petersburg", "peterburg": "Saint Petersburg", "sankt peterburg": "Saint Petersburg", "frankfurt": "Frankfurt",
    "sao paulo": "Sao Paulo", "tel aviv": "Tel Aviv-Yafo", "hanoi": "Hanoi", "bruxelles": "Brussels", "koln": "Cologne", "munchen": "Munich", "wien": "Vienna",
    "roma": "Rome", "praha": "Prague", "lisboa": "Lisbon", "moskva": "Moscow", "beijing": "Beijing", "mumbai": "Mumbai", "turin": "Torino", "napoli": "Naples",
}

# names that mean different places in everyday speech: without a qualifier ("Washington DC", "Georgia, USA") the answer would be a guess
NEVER_BARE = {"washington", "georgia", "korea"}

# stretches of the world the camera can frame (lon_min, lat_min, lon_max, lat_max)
FRAMES = {
    "world": (-180, -58, 180, 80), "the world": (-180, -58, 180, 80), "europe": (-11, 35, 40, 71), "africa": (-18, -35, 52, 37), "asia": (30, -10, 150, 55),
    "north america": (-168, 14, -52, 72), "south america": (-82, -56, -34, 13), "oceania": (110, -48, 180, 0), "australia and oceania": (110, -48, 180, 0),
    "middle east": (25, 12, 63, 42), "southeast asia": (92, -11, 141, 28), "south asia": (60, 5, 98, 37), "east asia": (73, 18, 146, 53), "central asia": (46, 35, 88, 56),
    "central america": (-93, 7, -77, 18), "caribbean": (-86, 9, -58, 28), "scandinavia": (4, 54, 32, 71), "balkans": (13, 34, 30, 47), "western europe": (-11, 36, 16, 61),
    "eastern europe": (14, 41, 41, 60), "latin america": (-118, -56, -34, 33), "sub saharan africa": (-18, -35, 52, 20), "north africa": (-18, 15, 40, 38),
    "mediterranean": (-6, 30, 37, 46), "the mediterranean": (-6, 30, 37, 46), "arctic": (-180, 62, 180, 90), "pacific": (120, -50, 240, 55), "the pacific": (120, -50, 240, 55),
    "atlantic": (-80, -40, 20, 60), "the atlantic": (-80, -40, 20, 60), "european union": (-11, 35, 32, 70), "the alps": (5, 43, 16, 48), "alps": (5, 43, 16, 48),
    "the caucasus": (36, 38, 52, 45), "caucasus": (36, 38, 52, 45), "horn of africa": (33, -2, 53, 19), "british isles": (-11, 49, 2, 61), "iberian peninsula": (-10, 35.5, 4, 44.5),
    "indian subcontinent": (60, 5, 98, 37), "gulf": (46, 22, 58, 31), "persian gulf": (46, 22, 58, 31), "west africa": (-18, 3, 16, 25), "east africa": (28, -12, 52, 18),
    "baltic": (9, 53, 31, 66), "the baltics": (20, 53, 29, 60), "baltic states": (20, 53, 29, 60),
}


# ----------------------------------------------------------------------------- offline index
@lru_cache(maxsize=1)
def _index() -> Dict[str, Any]:
    a0 = _geo.layer("adm0_50")
    a1 = _geo.layer("adm1")
    pl = _geo.places()
    country: Dict[str, List[int]] = {}
    for i, m in enumerate(a0.meta):
        for nm in m[_geo.A0_NAMES]:
            country.setdefault(fold(nm), []).append(i)
        for al in COUNTRY_ALIASES.get(m[_geo.A0_ID], []):
            country.setdefault(al, []).append(i)
        country.setdefault(fold(m[_geo.A0_NAME]), []).append(i)
    for k in list(country):
        country[k] = sorted(set(country[k]))
    iso3 = {str(m[_geo.A0_ISO3]).lower(): i for i, m in enumerate(a0.meta) if m[_geo.A0_ISO3] and m[_geo.A0_ISO3] != "-99"}
    admin1: Dict[str, List[int]] = {}
    for i, m in enumerate(a1.meta):
        for nm in m[_geo.A1_NAMES] or [m[_geo.A1_NAME]]:
            admin1.setdefault(fold(nm), []).append(i)
    for k in list(admin1):
        admin1[k] = sorted(set(admin1[k]))
    place: Dict[str, List[int]] = {}
    for i, r in enumerate(pl):
        for nm in [r[_geo.P_NAME]] + list(r[_geo.P_ALTS]):
            place.setdefault(fold(nm), []).append(i)
    for k in list(place):
        place[k] = sorted(set(place[k]))
    return {"country": country, "iso3": iso3, "admin1": admin1, "place": place, "a0": a0, "a1": a1, "pl": pl}


def country_by_id(cid: str) -> Optional[int]:
    a0 = _index()["a0"]
    for i, m in enumerate(a0.meta):
        if m[_geo.A0_ID] == cid:
            return i
    return None


def _country_names(i: int) -> List[str]:
    m = _index()["a0"].meta[i]
    return [fold(x) for x in m[_geo.A0_NAMES]] + [fold(m[_geo.A0_ISO3]), fold(m[_geo.A0_ISO2])] + [fold(a) for a in COUNTRY_ALIASES.get(m[_geo.A0_ID], [])]


def _cand_country_of(kind: str, i: int) -> List[str]:
    """Folded names of the country a candidate belongs to (for qualifiers like "Paris, France")."""
    ix = _index()
    if kind == "country":
        return _country_names(i)
    if kind == "admin1":
        m = ix["a1"].meta[i]
        ci = country_by_id(m[_geo.A1_ADM0])
        return (_country_names(ci) if ci is not None else []) + [fold(m[_geo.A1_COUNTRY])]
    r = ix["pl"][i]
    return [fold(r[_geo.P_COUNTRY]), fold(r[_geo.P_ISO2])]


def _cand_region_of(kind: str, i: int) -> List[str]:
    ix = _index()
    if kind == "admin1":
        return [fold(x) for x in ix["a1"].meta[i][_geo.A1_NAMES]]
    if kind == "place":
        return [fold(ix["pl"][i][_geo.P_ADM1])]
    return []


def _pop(kind: str, i: int) -> float:
    ix = _index()
    if kind == "country":
        return float(ix["a0"].meta[i][_geo.A0_POP])
    if kind == "place":
        return float(ix["pl"][i][_geo.P_POP])
    ci = country_by_id(ix["a1"].meta[i][_geo.A1_ADM0])          # a region weighs as much as its country: "Florida" is Florida, USA rather than Florida, Uruguay
    return float(ix["a0"].meta[ci][_geo.A0_POP]) if ci is not None else 0.0


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _entity(kind: str, i: int) -> Entity:
    ix = _index()
    if kind == "country":
        m = ix["a0"].meta[i]
        return {"t": "country", "id": m[_geo.A0_ID], "n": _clean(m[_geo.A0_NAME])}
    if kind == "admin1":
        m = ix["a1"].meta[i]
        return {"t": "admin1", "id": m[_geo.A1_ID], "n": _clean(m[_geo.A1_NAME]), "c": m[_geo.A1_ADM0]}
    r = ix["pl"][i]
    return {"t": "point", "lon": float(r[_geo.P_LON]), "lat": float(r[_geo.P_LAT]), "n": _clean(r[_geo.P_NAME]), "s": "ne"}


def _as_point(e: Entity) -> Entity:
    """A country or region used where a point is wanted (a pin on 'Brazil'): its label point."""
    ix = _index()
    if e["t"] == "country":
        m = ix["a0"].meta[country_by_id(e["id"])]
        return {"t": "point", "lon": float(m[_geo.A0_LX]), "lat": float(m[_geo.A0_LY]), "n": e["n"], "s": "country"}
    if e["t"] == "admin1":
        for m in ix["a1"].meta:
            if m[_geo.A1_ID] == e["id"]:
                return {"t": "point", "lon": float(m[_geo.A1_LX]), "lat": float(m[_geo.A1_LY]), "n": e["n"], "s": "admin1"}
    return e


TIERS = {"shape": ("country", "admin1"), "point": ("place", "country", "admin1"), "any": ("country", "admin1", "place")}


def resolve_offline(name: str, role: str = "any") -> Entity:
    """role: "shape" (a polygon to highlight: country or state), "point" (a pin: city, or the label point of a country/state), "any" (to frame: country, state, city, or a named
    stretch of the world). Raises NotFound or Ambiguous."""
    raw = str(name or "").strip()
    if not raw:
        raise NotFound("empty name")
    ix = _index()
    whole = fold(raw.replace(",", " "))
    if role != "shape" and whole in CITY_ALIASES:                   # "NYC", "Bombay", "Washington DC": a fixed answer
        key, qkey, base = fold(CITY_ALIASES[whole]), "", CITY_ALIASES[whole]
    else:
        base, _, qual = raw.partition(",")
        key, qkey = fold(base), fold(qual)
    if not key:
        raise NotFound(raw)
    if role == "any" and not qkey and key in FRAMES:
        return {"t": "frame", "box": list(FRAMES[key]), "n": base.strip()}
    if key in NEVER_BARE and not qkey and role != "shape":
        raise Ambiguous(f"{raw!r} could be several places; add the country or state")
    tiers = TIERS[role]
    uppercase_code = base.strip().isupper() and len(base.strip()) == 3 and base.strip().isalpha()
    for tier in tiers:
        idxs = list(ix[tier].get(key, []))
        if tier == "country" and not idxs and uppercase_code and key in ix["iso3"]:
            idxs = [ix["iso3"][key]]
        if not idxs:
            continue
        cands = [(tier, i) for i in idxs]
        if tier == "admin1":                    # only an area's own name counts: "Tuscany" is an alias of every province in it, not the name of one
            cands = [c for c in cands if key in {fold(ix["a1"].meta[c[1]][_geo.A1_NAME]), fold((ix["a1"].meta[c[1]][_geo.A1_NAMES] or [""])[0])}]
            if not cands:
                continue
        if qkey:
            cands = [c for c in cands if qkey in _cand_country_of(*c) or qkey in _cand_region_of(*c)]
            if not cands:
                continue
        e = _pick(key, cands, role)
        if e is not None:
            return e
    raise NotFound(raw)


def _pick(key: str, cands: List[Tuple[str, int]], role: str) -> Optional[Entity]:
    ix = _index()
    tier = cands[0][0]
    if len(cands) > 1:
        cands = sorted(cands, key=lambda c: -_pop(*c))
        top, second = _pop(*cands[0]), _pop(*cands[1])
        if tier == "place":
            a, b = ix["pl"][cands[0][1]], ix["pl"][cands[1][1]]
            same_spot = abs(a[_geo.P_LON] - b[_geo.P_LON]) < 0.6 and abs(a[_geo.P_LAT] - b[_geo.P_LAT]) < 0.6
            if not same_spot and not (top > 0 and top >= 5 * max(second, 1)):
                raise Ambiguous(f"{key!r} matches several places")
        elif tier == "country":
            if not (top >= 5 * max(second, 1)):
                raise Ambiguous(f"{key!r} matches several countries")
        else:
            same_country = len({ix["a1"].meta[i][_geo.A1_ADM0] for _, i in cands}) == 1
            if not same_country and not (top > 0 and top >= 5 * max(second, 1)):
                raise Ambiguous(f"{key!r} is a region in several countries; add the country")
            cands = cands[:1]
    kind, i = cands[0]
    e = _entity(kind, i)
    if kind == "country" and role != "point":
        # a country whose name is also a state elsewhere in a big country ("Georgia"): the bare name is a guess
        for j in ix["admin1"].get(key, []):
            m = ix["a1"].meta[j]
            if m[_geo.A1_ADM0] != e["id"] and m[_geo.A1_ADM0] in ("USA", "CAN", "AUS", "BRA", "IND", "RUS", "CHN", "MEX"):
                raise Ambiguous(f"{key!r} is both a country and a region of {m[_geo.A1_COUNTRY]}")
    if role == "point" and kind != "place":
        e = _as_point(e)
    return e


# ----------------------------------------------------------------------------- Wikidata (CC0)
def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (fixed https host)
        return json.loads(r.read().decode("utf-8"))


_WD_CACHE: Dict[str, Entity] = {}


def _norm_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def wikidata_lookup(name: str, http: Optional[Callable[..., Dict[str, Any]]] = None) -> Entity:
    """Coordinates of a landmark or small town by its English name. Accepts only an exact (accent- and case-insensitive) match of a label or alias that has Earth coordinates;
    several exact matches must be within 50 km of each other, otherwise the name is ambiguous. Raises NotFound / Ambiguous / ResolveError (network)."""
    http = http or _http_json
    raw = str(name).strip()
    base, _, qual = raw.partition(",")
    key, qkey = fold(base), fold(qual)
    if not key:
        raise NotFound(raw)
    ck = f"{key}|{qkey}"
    if ck in _WD_CACHE:
        return dict(_WD_CACHE[ck])
    try:
        q = urllib.parse.urlencode({"action": "wbsearchentities", "search": base.strip(), "language": "en", "uselang": "en", "format": "json", "limit": 8, "type": "item"})
        found = http(f"{WD_API}?{q}", HTTP_TIMEOUT).get("search") or []
        exact = []
        for r in found:
            texts = [r.get("label")] + [a for a in (r.get("aliases") or [])] + [(r.get("match") or {}).get("text")]
            if key in {fold(t) for t in texts if t}:
                if qkey and qkey not in fold(r.get("description") or ""):
                    continue
                exact.append(r)
        if not exact:
            raise NotFound(raw)
        ids = "|".join(r["id"] for r in exact[:5])
        q2 = urllib.parse.urlencode({"action": "wbgetentities", "ids": ids, "props": "claims|labels", "languages": "en", "format": "json"})
        ents = http(f"{WD_API}?{q2}", HTTP_TIMEOUT).get("entities") or {}
    except ResolveError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ResolveError(f"Wikidata unavailable: {type(e).__name__}") from e
    pts: List[Tuple[float, float, str]] = []
    for r in exact[:5]:
        ent = ents.get(r["id"]) or {}
        for cl in (ent.get("claims") or {}).get("P625", []):
            if cl.get("rank") == "deprecated":
                continue
            v = ((cl.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
            if "latitude" in v and "longitude" in v and str(v.get("globe", "")).endswith("/Q2"):
                lat, lon = float(v["latitude"]), float(v["longitude"])
                if math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180:
                    pts.append((lon, lat, ((ent.get("labels") or {}).get("en") or {}).get("value") or base.strip()))
                    break
    if not pts:
        raise NotFound(raw)
    from ._project import angular_distance_deg
    for p in pts[1:]:
        if angular_distance_deg(pts[0][0], pts[0][1], p[0], p[1]) > 0.45:       # about 50 km
            raise Ambiguous(f"{raw!r} matches several places on Wikidata")
    lon, lat, label = pts[0]
    e = {"t": "point", "lon": round(_norm_lon(lon), 5), "lat": round(lat, 5), "n": base.strip() or label, "s": "wd"}
    _WD_CACHE[ck] = e
    return dict(e)


def resolve(name: str, role: str = "any", allow_network: bool = False, http: Optional[Callable[..., Dict[str, Any]]] = None) -> Entity:
    """Offline first; for points (and framing) a name that Natural Earth does not know goes to Wikidata when `allow_network`. Ambiguity never falls through to the network."""
    try:
        return resolve_offline(name, role)
    except Ambiguous:
        raise
    except NotFound:
        if role == "shape" or not allow_network:
            raise
    return wikidata_lookup(name, http)
