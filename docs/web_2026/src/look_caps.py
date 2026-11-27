"""The `looks.look` and `looks.cast` objects of GET .../capabilities, built by the SERVER'S OWN code (lambdas/common/look_choice.py, capabilities_api.presenter) with
every look switched on, in English and Spanish: the mock for the web's look picker until QA serves them. No AWS call is made (boto3 is stubbed).
usage: python3 docs/web_2026/src/look_caps.py <out.json>     (run from the repository root)"""
import json, os, sys, types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend", "lambdas"))


class _Any:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Any()
    def __getattr__(self, n): return _Any()


for name in ("boto3", "botocore", "botocore.exceptions", "botocore.config", "boto3.dynamodb", "boto3.dynamodb.conditions", "boto3.dynamodb.types"):
    sys.modules.setdefault(name, types.ModuleType(name))
for n in ("client", "resource", "Session"): setattr(sys.modules["boto3"], n, _Any())
sys.modules["botocore.exceptions"].ClientError = Exception
sys.modules["botocore.config"].Config = _Any
for n in ("Key", "Attr"): setattr(sys.modules["boto3.dynamodb.conditions"], n, _Any())
for n in ("TypeDeserializer", "TypeSerializer"): setattr(sys.modules["boto3.dynamodb.types"], n, _Any)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from common import look_choice, looks  # noqa: E402
import capabilities_api  # noqa: E402

flags = {k: True for k in looks.flags()}
out = {loc: look_choice.capabilities(loc, capabilities_api.presenter(loc, True).get("cast") or [], f=flags) for loc in ("en", "es")}
json.dump(out, open(sys.argv[1], "w"))
print("wrote", sys.argv[1], {loc: [o["label"] for o in d["look"]["options"]] for loc, d in out.items()})
