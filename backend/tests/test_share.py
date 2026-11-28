"""Share links (docs/SHARE_PREVIEWS_2026-11-28.md): the page's tags and escaping, the owner-only create / revoke API on fake AWS, and the small stack's shape."""
import html
import json
import os
import re
import sys

import boto3
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from share import share_api, share_page  # noqa: E402

HOST = "share.example.com"
USER, OTHER = "u-owner-1", "u-other-2"
VID = "v-123"
ASSETS, SHARE = "videomk-qa-1", "videomk-qa-share-bucket"


# ----------------------------------------------------------------------------- the page
def page(**kw):
    return share_page.render(host=HOST, token=share_page.new_token(), title="How coffee is made", description="Beans, roast, brew.", **kw)


def test_token_is_unguessable_and_valid():
    ts = {share_page.new_token() for _ in range(200)}
    assert len(ts) == 200 and all(share_page.valid_token(t) and len(t) == 22 for t in ts)
    for bad in ("", "short", "a" * 23, "../" + "a" * 19, None, 5):
        assert not share_page.valid_token(bad)


def test_page_has_the_preview_tags():
    h = page()
    for need in ('property="og:title" content="How coffee is made"', 'property="og:description"', 'property="og:image" content="https://share.example.com/', '/og.jpg"',
                 'property="og:image:width" content="1200"', 'property="og:image:height" content="630"', 'name="twitter:card" content="summary_large_image"',
                 'name="twitter:image"', 'rel="canonical"', 'property="og:url"', 'name="robots" content="noindex, nofollow"', "<video controls", "poster="):
        assert need in h, need
    assert "og:video" not in h and "<script" not in h   # no player tag by default; nothing runs on the page


def test_page_without_cover_degrades_to_a_summary_card():
    h = page(has_cover=False, has_poster=False)
    assert "og:image" not in h and 'twitter:card" content="summary"' in h and "poster=" not in h


def test_page_escapes_what_a_person_wrote():
    h = share_page.render(host=HOST, token=share_page.new_token(), title='"><script>alert(1)</script>', description="<img src=x onerror=1>\nline", language="es")
    assert "<script>" not in h and "<img" not in h and "&lt;script&gt;" in h and 'lang="es"' in h


def test_page_has_nothing_personal_and_rejects_bad_input():
    h = page()
    assert USER not in h and VID not in h and not re.search(r"[\w.]+@[\w.]+\.\w+", h)
    with pytest.raises(ValueError):
        share_page.render(host=HOST, token="nope", title="x")
    with pytest.raises(ValueError):
        share_page.render(host="a.com/\"x", token=share_page.new_token(), title="x")


def test_blurb_takes_the_first_paragraph_without_links_or_chapters():
    d = "Beans and brewing https://x.example/y in one minute.\n\n0:00 Intro\n0:10 Roast"
    assert share_page.blurb(d) == "Beans and brewing in one minute."
    assert len(share_page.blurb("word " * 200)) <= share_page.DESC_MAX


# ----------------------------------------------------------------------------- the API, on fake AWS
@pytest.fixture
def aws(monkeypatch):
    from moto import mock_aws
    with mock_aws():
        for k, v in (("AWS_ACCESS_KEY_ID", "x"), ("AWS_SECRET_ACCESS_KEY", "x"), ("AWS_DEFAULT_REGION", "us-east-1")):
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("VIDEOS_TABLE", "videos")
        monkeypatch.setenv("ASSETS_BUCKET", ASSETS)
        monkeypatch.setenv("SHARE_BUCKET", SHARE)
        monkeypatch.setenv("SHARE_HOST", HOST)
        monkeypatch.delenv("DISTRIBUTION_ID", raising=False)
        s3 = boto3.client("s3")
        for b in (ASSETS, SHARE):
            s3.create_bucket(Bucket=b)
        base = f"videos/{USER}/{VID}/"
        s3.put_object(Bucket=ASSETS, Key=base + "final.mp4", Body=b"MP4DATA")
        s3.put_object(Bucket=ASSETS, Key=base + "r1_og.jpg", Body=b"OGJPG")
        s3.put_object(Bucket=ASSETS, Key=base + "r1_cover.jpg", Body=b"COVERJPG")
        s3.put_object(Bucket=ASSETS, Key="videos/someone-else/secret.mp4", Body=b"SECRET")
        ddb = boto3.resource("dynamodb")
        ddb.create_table(TableName="videos", KeySchema=[{"AttributeName": "video_id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "video_id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
        t = ddb.Table("videos")
        t.put_item(Item={"video_id": VID, "user_id": USER, "status": "COMPLETE", "title": "My <b>video</b>", "youtube_description": "A short story.\n\n0:00 Intro", "aspect": "9:16", "duration_s": 30,
                         "video_uri": f"s3://{ASSETS}/{base}final.mp4", "cover_og_uri": f"s3://{ASSETS}/{base}r1_og.jpg", "cover_uri": f"s3://{ASSETS}/{base}r1_cover.jpg"})
        yield s3, t


def ev(method, user=USER, path_user=USER, video=VID):
    return {"requestContext": {"http": {"method": method}, "authorizer": {"jwt": {"claims": {"sub": user}}} if user else {}}, "pathParameters": {"user_id": path_user, "video_id": video}}


def call(method, **kw):
    r = share_api.handler(ev(method, **kw))
    return r["statusCode"], json.loads(r["body"])


def keys(s3, bucket):
    return sorted(o["Key"] for o in s3.list_objects_v2(Bucket=bucket).get("Contents", []))


def test_create_copies_files_writes_page_and_is_idempotent(aws):
    s3, t = aws
    assert call("GET") == (200, {"shared": False})
    code, b = call("POST")
    assert code == 200 and b["shared"] and share_page.valid_token(b["token"]) and b["url"] == f"https://{HOST}/{b['token']}"
    tok = b["token"]
    assert keys(s3, SHARE) == sorted(f"{tok}/{n}" for n in share_page.FILES)
    assert s3.get_object(Bucket=SHARE, Key=f"{tok}/video.mp4")["Body"].read() == b"MP4DATA"
    assert s3.get_object(Bucket=SHARE, Key=f"{tok}/og.jpg")["ContentType"] == "image/jpeg"
    h = s3.get_object(Bucket=SHARE, Key=f"{tok}/index.html")["Body"].read().decode()
    assert "<b>video</b>" not in h and html.escape("My <b>video</b>") in h and "A short story." in h and "0:00" not in h and USER not in h and VID not in h
    assert t.get_item(Key={"video_id": VID})["Item"]["share_token"] == tok
    assert call("POST") == (200, b) and call("GET") == (200, b)   # same address the second time


def test_revoke_deletes_everything_and_clears_the_record(aws):
    s3, t = aws
    tok = call("POST")[1]["token"]
    assert call("DELETE") == (200, {"shared": False, "was_shared": True})
    assert keys(s3, SHARE) == [] and "share_token" not in t.get_item(Key={"video_id": VID})["Item"]
    assert call("GET") == (200, {"shared": False}) and call("DELETE")[1]["was_shared"] is False
    new = call("POST")[1]["token"]
    assert new != tok   # sharing again makes a NEW address: the old one stays dead


def test_only_the_owner_may_share_or_revoke(aws):
    s3, _t = aws
    assert call("POST", user=None)[0] == 401
    assert call("POST", user=OTHER, path_user=USER)[0] == 403
    assert call("POST", user=OTHER, path_user=OTHER)[0] == 404   # someone else's video id: looks like it does not exist
    tok = call("POST")[1]["token"]
    assert call("DELETE", user=OTHER, path_user=OTHER)[1]["was_shared"] is False and keys(s3, SHARE)
    assert call("GET", user=OTHER, path_user=OTHER)[0] == 404 and tok


def test_not_ready_and_foreign_objects_are_refused(aws):
    s3, t = aws
    t.update_item(Key={"video_id": VID}, UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":s": "PROCESSING"})
    assert call("POST") == (409, {"code": "not_ready"})
    t.update_item(Key={"video_id": VID}, UpdateExpression="SET #s = :s, video_uri = :u", ExpressionAttributeNames={"#s": "status"},
                  ExpressionAttributeValues={":s": "COMPLETE", ":u": f"s3://{ASSETS}/videos/someone-else/secret.mp4"})
    assert call("POST") == (409, {"code": "not_ready"}) and keys(s3, SHARE) == []   # a record pointing outside the video's own folder is never copied


def test_older_video_without_covers_still_shares(aws):
    s3, t = aws
    t.update_item(Key={"video_id": VID}, UpdateExpression="REMOVE cover_uri, cover_og_uri")
    tok = call("POST")[1]["token"]
    assert keys(s3, SHARE) == sorted(f"{tok}/{n}" for n in ("index.html", "video.mp4"))
    assert "og:image" not in s3.get_object(Bucket=SHARE, Key=f"{tok}/index.html")["Body"].read().decode()


# ----------------------------------------------------------------------------- the stack
def test_stack_shape(tmp_path):
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    from share_stack import PAGE_FUNCTION, ShareStack
    app = cdk.App(outdir=str(tmp_path / "out"))
    st = ShareStack(app, "videomk-qa-share", stage="qa", videos_table_name="vt", assets_bucket="videomk-qa-123456789012", user_pool_id="eu-west-1_abc", client_ids=["c1"],
                    bundle_dir=str(tmp_path / "b"), env=cdk.Environment(account="123456789012", region="eu-west-1"))
    t = Template.from_stack(st).to_json()
    res = t["Resources"]
    assert len(res) < 40
    of = lambda typ: [v for v in res.values() if v["Type"] == typ]   # noqa: E731
    (bkt,) = [v for v in of("AWS::S3::Bucket")]
    assert bkt["Properties"]["PublicAccessBlockConfiguration"]["BlockPublicPolicy"] is True
    (dist,) = of("AWS::CloudFront::Distribution")
    assert dist["Properties"]["DistributionConfig"]["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    assert dist["Properties"]["DistributionConfig"]["DefaultCacheBehavior"]["AllowedMethods"] == ["GET", "HEAD"]
    (auth,) = of("AWS::ApiGatewayV2::Authorizer")
    assert auth["Properties"]["AuthorizerType"] == "JWT"
    routes = [r["Properties"] for r in of("AWS::ApiGatewayV2::Route")]
    assert {r["RouteKey"] for r in routes} == {f"{m} /users/{{user_id}}/videos/{{video_id}}/share" for m in ("GET", "POST", "DELETE")}
    assert all(r["AuthorizationType"] == "JWT" for r in routes)   # nothing public on the API
    assert os.path.exists(tmp_path / "b" / "share_api.py") and os.path.exists(tmp_path / "b" / "share_page.py")
    assert "index.html" in PAGE_FUNCTION
    # the function can read ONLY the videos folder of the assets bucket
    pol = json.dumps([v for v in of("AWS::IAM::Policy")])
    assert "videomk-qa-123456789012/videos/*" in pol and "table/vt" in pol


def test_page_function_maps_token_to_index():
    import shutil
    import subprocess
    from share_stack import PAGE_FUNCTION
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    tok = share_page.new_token()
    js = PAGE_FUNCTION + f"\nfor (const u of ['/{tok}','/{tok}/','/{tok}/og.jpg','/other']) console.log(handler({{request:{{uri:u}}}}).uri);"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout.split()
    assert out == [f"/{tok}/index.html", f"/{tok}/index.html", f"/{tok}/og.jpg", "/other"]


# ----------------------------------------------------------------------------- the designed cover (engine/cover.py), from a synthetic first scene
@pytest.mark.parametrize("aspect,size", [("16:9", (1920, 1080)), ("9:16", (1080, 1920)), ("1:1", (1080, 1080)), ("4:5", (1080, 1350))])
def test_cover_card_shapes_and_sizes(aspect, size):
    import io
    from PIL import Image
    from engine import cover
    art = Image.new("RGB", size, (240, 238, 230))   # blank paper: the very first frame that used to be the preview
    out = cover.build_from_art(art, "How coffee is made, from bean to cup in one minute", aspect=aspect, theme="paper")
    og = Image.open(io.BytesIO(out["og"]))
    assert og.size == (cover.OG_W, cover.OG_H) and len(out["og"]) <= cover.OG_MAX_BYTES
    own = Image.open(io.BytesIO(out["own"]))
    assert abs(own.width / own.height - size[0] / size[1]) < 0.01 and max(own.size) <= cover.OWN_LONG_SIDE and len(out["own"]) <= cover.OWN_MAX_BYTES
    assert og.convert("L").getextrema()[0] < 120   # the title's ink is on the card: it is not a blank page any more
