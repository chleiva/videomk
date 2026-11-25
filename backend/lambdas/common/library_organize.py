"""Smart collections: organise photos by place and time with plain rules (no AI), and keep later uploads in step. See docs/MEDIA_LIBRARY.md.

Rules (deterministic, so the same photos always give the same collections):
  * the HOME place is the person's most frequent place (at least 20 photos and a quarter of the photos that have a place); photos taken there are grouped by month:
    "London - Apr 2026"; photos with no place are grouped by month alone: "Apr 2026";
  * photos taken elsewhere form TRIPS: per place, photos within GAP_DAYS of each other are one trip: "Phuket - 14-21 Jul 2024" (a trip over a month end stays one collection);
  * a group with fewer than MIN_GROUP photos is not made (those photos stay as they are), unless it joins a collection that already exists;
  * a later photo joins an existing automatic collection when it matches (same place and month, or inside a trip's dates plus GAP_DAYS), else it starts a new group.
The preview never writes; the apply step works in chunks (LIMIT photos a call) so a library of 10,000 photos is organised by repeated calls, each one safe to repeat.
"""
import datetime
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from boto3.dynamodb.conditions import Key

from common import library as lib

GAP_DAYS = 4
MIN_GROUP = 5
HOME_MIN = 20
HOME_SHARE = 0.25
LIMIT = 300
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SINCE_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")


def _day(row: Dict[str, Any]) -> str:
    return (row.get("taken") or row.get("added") or "")[:10]


def _date(day: str) -> datetime.date:
    return datetime.date.fromisoformat(day)


def city(place_key: str) -> str:
    return place_key.split(",")[0].strip()


def month_name(ym: str) -> str:
    return f"{MONTHS[int(ym[5:7]) - 1]} {ym[:4]}"


def trip_name(pk: str, start: str, end: str) -> str:
    a, b = _date(start), _date(end)
    if a == b:
        span = f"{a.day} {MONTHS[a.month - 1]} {a.year}"
    elif (a.year, a.month) == (b.year, b.month):
        span = f"{a.day}-{b.day} {MONTHS[a.month - 1]} {a.year}"
    elif a.year == b.year:
        span = f"{a.day} {MONTHS[a.month - 1]} - {b.day} {MONTHS[b.month - 1]} {a.year}"
    else:
        span = f"{a.day} {MONTHS[a.month - 1]} {a.year} - {b.day} {MONTHS[b.month - 1]} {b.year}"
    return f"{city(pk)} · {span}"[:40]


def month_group_name(pk: str, ym: str) -> str:
    return f"{city(pk)} · {month_name(ym)}"[:40] if pk else month_name(ym)


def home_place(user: str) -> Optional[str]:
    places = lib.facets(user)["p"]
    if not places:
        return None
    top, n = max(places.items(), key=lambda kv: kv[1])
    return top if n >= HOME_MIN and n >= HOME_SHARE * sum(places.values()) else None


def existing_auto(user: str) -> List[Dict[str, Any]]:
    res = lib.table().query(KeyConditionExpression=Key("user_id").eq(lib.check_user(user)) & Key("sk").begins_with("c#"))
    return [{"id": c["sk"][2:], "auto": dict(c["auto"]), "name": c["nm"], "ren": bool(c.get("ren")), "n": int(c.get("n") or 0)} for c in res.get("Items", []) if c.get("auto")]


def _match(existing: List[Dict[str, Any]], pk: str, day: str, home: Optional[str]) -> Optional[Dict[str, Any]]:
    """The existing automatic collection a photo belongs in by the rules, if any."""
    ym = day[:7]
    d = _date(day)
    best, best_gap = None, None
    for c in existing:
        a = c["auto"]
        if (a.get("pk") or "") != pk:
            continue
        if a.get("k") == "m" and a.get("ym") == ym and (not pk or pk == home):
            return c
        if a.get("k") == "t" and a.get("from") and a.get("to") and pk != home:
            lo, hi = _date(a["from"]) - datetime.timedelta(days=GAP_DAYS), _date(a["to"]) + datetime.timedelta(days=GAP_DAYS)
            if lo <= d <= hi:
                gap = 0 if _date(a["from"]) <= d <= _date(a["to"]) else min(abs((d - _date(a["from"])).days), abs((d - _date(a["to"])).days))
                if best is None or gap < best_gap:
                    best, best_gap = c, gap
    return best


def plan_groups(rows: List[Dict[str, Any]], home: Optional[str], existing: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure: {"groups": [{"key", "existing_id", "auto", "name", "rows"}], "skipped": [rows]} for these photo rows (oldest first)."""
    rows = sorted(rows, key=lambda r: r.get("srt") or "")
    joined: Dict[str, Dict[str, Any]] = {}       # existing collection id -> group
    months: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    trips: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        day = _day(r)
        if len(day) != 10:
            continue
        pk = r.get("plk") or ""
        c = _match(existing, pk, day, home)
        if c is not None:
            g = joined.setdefault(c["id"], {"key": f"e:{c['id']}", "existing_id": c["id"], "auto": dict(c["auto"]), "name": c["name"], "ren": c["ren"], "rows": []})
            g["rows"].append(r)
        elif pk and pk != home:
            trips.setdefault(pk, []).append(r)
        else:
            months.setdefault((pk, day[:7]), []).append(r)
    groups: List[Dict[str, Any]] = list(joined.values())
    for g in groups:   # a trip that gained earlier or later photos grows its dates (and its name, unless the person renamed it)
        a = g["auto"]
        if a.get("k") == "t":
            days = [_day(r) for r in g["rows"]]
            a["from"], a["to"] = min([a["from"]] + days), max([a["to"]] + days)
            if not g.get("ren"):
                g["name"] = trip_name(a["pk"], a["from"], a["to"])
    skipped: List[Dict[str, Any]] = []
    for (pk, ym), rs in sorted(months.items(), key=lambda kv: kv[0][1]):
        if len(rs) < MIN_GROUP:
            skipped += rs
            continue
        groups.append({"key": f"m:{pk}:{ym}", "existing_id": None, "auto": {"k": "m", "pk": pk, "ym": ym}, "name": month_group_name(pk, ym), "rows": rs})
    for pk, rs in trips.items():
        cur: List[Dict[str, Any]] = []
        for r in rs + [None]:
            if r is not None and cur and (_date(_day(r)) - _date(_day(cur[-1]))).days <= GAP_DAYS:
                cur.append(r)
                continue
            if cur:
                if len(cur) < MIN_GROUP:
                    skipped += cur
                else:
                    a, b = _day(cur[0]), _day(cur[-1])
                    groups.append({"key": f"t:{pk}:{a}", "existing_id": None, "auto": {"k": "t", "pk": pk, "from": a, "to": b}, "name": trip_name(pk, a, b), "rows": cur})
            cur = [r] if r is not None else []
    groups.sort(key=lambda g: g["rows"][0].get("srt") or "", reverse=True)
    return {"groups": groups, "skipped": skipped}


# ----------------------------------------------------------------------------- which photos
def candidates(user: str, *, since: Optional[str] = None, without: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ready photos, oldest first: those added since a moment (a batch just uploaded) or all; for automatic organising only those in no collection yet,
    for 'put them all in one collection' only those not yet in that collection (`without`)."""
    if since is not None and not SINCE_RE.match(since):
        raise lib.LibraryError(400, "'since' must look like 2026-11-25T09:00:00")
    rows: List[Dict[str, Any]] = []
    start = None
    while True:
        kw: Dict[str, Any] = {"IndexName": "Timeline", "KeyConditionExpression": Key("user_id").eq(user), "ScanIndexForward": True,
                              "ProjectionExpression": "sk, srt, taken, added, plk, cc, cols"}
        if start:
            kw["ExclusiveStartKey"] = start
        res = lib.table().query(**kw)
        rows += res.get("Items", [])
        start = res.get("LastEvaluatedKey")
        if not start:
            break
    out = []
    for r in rows:
        if since is not None and (r.get("added") or "") < since:
            continue
        cols = r.get("cols") or set()
        if without is not None:
            if without in cols:
                continue
        elif cols:
            continue
        out.append(r)
    return out


def preview(user: str, since: Optional[str] = None) -> Dict[str, Any]:
    lib.check_user(user)
    rows = candidates(user, since=since)
    home = home_place(user)
    p = plan_groups(rows, home, existing_auto(user))
    groups = [{"name": g["name"], "count": len(g["rows"]), "existing": bool(g["existing_id"]), "sample_ids": [r["sk"][2:] for r in g["rows"][-3:]]} for g in p["groups"]]
    return {"total": len(rows), "organized": sum(g["count"] for g in groups), "skipped": len(p["skipped"]), "groups": groups, "home": city(home) if home else None}


# ----------------------------------------------------------------------------- writing
def bulk_add(user: str, cid: str, rows: List[Dict[str, Any]]) -> int:
    """Puts photos in a collection in bulk (membership rows, each photo's list, the count and the cover). Safe to repeat: photos already in are left alone. Returns how many were new."""
    if not rows:
        return 0
    rows = [r for r in rows if r.get("srt")]
    keys = [{"user_id": user, "sk": f"cm#{cid}#{r['srt']}"} for r in rows]
    have = set()
    for n in range(0, len(keys), 100):
        req = {lib.table().name: {"Keys": keys[n:n + 100], "ProjectionExpression": "sk"}}
        for _ in range(5):
            res = lib.ddb().batch_get_item(RequestItems=req)
            have |= {it["sk"] for it in res["Responses"].get(lib.table().name, [])}
            req = res.get("UnprocessedKeys") or {}
            if not req:
                break
    new = [r for r in rows if f"cm#{cid}#{r['srt']}" not in have]
    if not new:
        return 0
    with lib.table().batch_writer() as bw:
        for r in new:
            bw.put_item(Item={"user_id": user, "sk": f"cm#{cid}#{r['srt']}", "mid": r["sk"][2:]})
    client = lib.ddb().meta.client

    def tag(r: Dict[str, Any]) -> None:
        client.update_item(TableName=lib.table().name, Key={"user_id": user, "sk": r["sk"]}, UpdateExpression="ADD cols :c", ExpressionAttributeValues={":c": {cid}})

    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(tag, new))
    newest = max(new, key=lambda r: r["srt"])["sk"][2:]
    lib.table().update_item(Key={"user_id": user, "sk": f"c#{cid}"}, UpdateExpression="ADD n :k SET cover = :m", ExpressionAttributeValues={":k": len(new), ":m": newest})
    return len(new)


def apply_auto(user: str, since: Optional[str] = None, limit: int = LIMIT) -> Dict[str, Any]:
    """Organises about `limit` photos by the rules and reports what is left; the app calls again until `remaining` is 0. The plan is made over ALL the candidate photos each time
    (so a group is never cut in two and judged too small), whole groups are applied in order, and a group bigger than the budget is applied in parts: its later part then matches the
    collection the first part created. Photos that belong to no group stay as they are and are not counted as remaining."""
    lib.check_user(user)
    rows = candidates(user, since=since)
    existing = existing_auto(user)
    p = plan_groups(rows, home_place(user), existing)
    budget = max(1, min(int(limit), LIMIT))
    total_cols = len(lib.collections(user))
    created = updated = applied = left = 0
    for g in p["groups"]:
        part = g["rows"][:budget] if budget > 0 else []
        if not part:
            left += len(g["rows"])
            continue
        cid = g["existing_id"]
        if cid is None:
            cid = lib.create_collection(user, g["name"], None, g["auto"], count_hint=total_cols)["id"]
            total_cols += 1
            created += 1
        else:
            updated += 1
            vals: Dict[str, Any] = {":a": g["auto"]}
            sets = ["#a = :a"]   # "auto" is a reserved word in DynamoDB expressions
            if not g.get("ren"):
                sets.append("nm = :n")
                vals[":n"] = g["name"]
            lib.table().update_item(Key={"user_id": user, "sk": f"c#{cid}"}, UpdateExpression="SET " + ", ".join(sets), ExpressionAttributeNames={"#a": "auto"}, ExpressionAttributeValues=vals)
        n = bulk_add(user, cid, part)
        applied += len(part)
        budget -= len(part)
        left += len(g["rows"]) - len(part)
    return {"applied": applied, "remaining": left, "created": created, "updated": updated, "skipped": len(p["skipped"])}


def apply_single(user: str, name: Any, since: Optional[str] = None, collection_id: Optional[str] = None, limit: int = LIMIT) -> Dict[str, Any]:
    """Puts the photos of a batch (or all unorganised photos) in ONE collection (a new one named `name`, or an existing one), in chunks."""
    lib.check_user(user)
    if collection_id:
        cid = lib.check_id(collection_id)
        lib._collection(user, cid)
        made = 0
    else:
        cid = lib.create_collection(user, name)["id"]
        made = 1
    rows = candidates(user, since=since, without=cid)
    chunk = rows[: max(1, min(int(limit), LIMIT))]
    added = bulk_add(user, cid, chunk)
    return {"collection_id": cid, "applied": added, "remaining": max(0, len(rows) - len(chunk)), "created": made}
