"""The whiteboard TRACER function in a stack of its own (docs/LIBRARY_ON_DEMAND.md, part D):

    backend/layers/build_layer.sh tracer_deps
    cdk deploy videomk-<stage>-wb-tracer -c stage=<stage> -c objectTracer=1

Why its own stack: sketch objects cannot be made in the engine's functions (the tracer's scipy and vtracer do not fit the engine layer: 148 MB + about 100 MB
against the 250 MB a function may unpack), and the main stack is near the 500-resource limit. This stack has one function, its layer, its role and its log
group. The main stack only learns the function's NAME (one variable and one `lambda:InvokeFunction` statement on the plan function, under the clipsOnDemand
flag): there is no cross-stack reference, so either stack deploys or is deleted without the other. With this stack absent the plan step's call fails and the
boards keep their written labels.

A zip function with a layer, not a container image: every dependency is a manylinux wheel (the same way the engine layer is built), so nothing needs Docker or
a registry. The function's code is assembled at synth time from the files it needs (`bundle()`): the maker and the policy from lambdas/common, the model client,
one font, and the library builder's own tracing code from scripts/whiteboard_proto.
"""
import os
import shutil
from typing import Optional

from aws_cdk import Duration, RemovalPolicy, Stack, aws_iam as iam, aws_lambda as _lambda, aws_logs as logs
from constructs import Construct

HERE = os.path.dirname(os.path.abspath(__file__))
OPENAI_SSM_PARAM = "/videomk/openai_api_key"

# what the function needs, as (path in this repository's backend/, path in the bundle). The bundle mirrors the repository so the builder's own relative paths hold.
FILES = (
    ("tracer/handler.py", "handler.py"),
    ("lambdas/common/__init__.py", "lambdas/common/__init__.py"),
    ("lambdas/common/object_maker.py", "lambdas/common/object_maker.py"),
    ("lambdas/common/media_policy.py", "lambdas/common/media_policy.py"),
    ("lambdas/common/catalog_make.py", "lambdas/common/catalog_make.py"),
    ("lambdas/engine/llm.py", "lambdas/engine/llm.py"),
    ("lambdas/engine/assets/fonts/Inter-SemiBold.ttf", "lambdas/engine/assets/fonts/Inter-SemiBold.ttf"),
    ("scripts/whiteboard_proto/lib_build.py", "scripts/whiteboard_proto/lib_build.py"),
    ("scripts/whiteboard_proto/trace.py", "scripts/whiteboard_proto/trace.py"),
    ("scripts/whiteboard_proto/vectorize.py", "scripts/whiteboard_proto/vectorize.py"),
    ("scripts/whiteboard_proto/gen_art.py", "scripts/whiteboard_proto/gen_art.py"),
    ("scripts/whiteboard_proto/lib_plan.py", "scripts/whiteboard_proto/lib_plan.py"),
    ("scripts/whiteboard_proto/wbcommon.py", "scripts/whiteboard_proto/wbcommon.py"),
)


def function_name(stage: str) -> str:
    """The one thing the two stacks share: the main stack gives this name to the plan function, this stack gives it to the tracer."""
    return f"videomk-{stage}-wb-tracer"


def bundle(out_dir: Optional[str] = None) -> str:
    """Assemble the function's code folder (a few hundred KB) and return its path. Rebuilt from scratch every time, so it always matches the working tree."""
    out = out_dir or os.path.join(HERE, "build", "wb_tracer")
    shutil.rmtree(out, ignore_errors=True)
    for src, dst in FILES:
        target = os.path.join(out, dst)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(HERE, src), target)
    with open(os.path.join(out, "lambdas", "engine", "__init__.py"), "w") as f:   # the engine package's own __init__ is only a docstring; the function needs just `engine.llm`
        f.write('"""The model client of the engine (llm.py), bundled for the whiteboard tracer function."""\n')
    return out


class ObjectTracerStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, stage: str, plan_model_id: str = "", bundle_dir: Optional[str] = None, **kw) -> None:
        super().__init__(scope, cid, **kw)
        layer_dir = os.path.join(HERE, "layers", "tracer_deps")
        if not os.path.isdir(os.path.join(layer_dir, "python")) and not os.environ.get("CDK_SKIP_LAYER_CHECK"):
            raise ValueError("Tracer layer not built. Run `backend/layers/build_layer.sh tracer_deps` first (or set CDK_SKIP_LAYER_CHECK=1 for a synth-only check).")
        layer = _lambda.LayerVersion(self, "TracerDepsLayer", code=_lambda.Code.from_asset(layer_dir), compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
                                     compatible_architectures=[_lambda.Architecture.X86_64], description="Whiteboard tracer: numpy, scipy, Pillow, vtracer, resvg")
        name = function_name(stage)
        log_group = logs.LogGroup(self, "TracerLogs", log_group_name=f"/aws/lambda/{name}", retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.DESTROY)
        env = {"OPENAI_SSM_PARAM": OPENAI_SSM_PARAM, "WB_OUT": "/tmp/wb"}
        if plan_model_id:
            env["PLAN_MODEL_ID"] = plan_model_id   # the gate's model, when the stage overrides it for the engine (-c planModelId=...)
        self.fn = _lambda.Function(
            self, "TracerFn", function_name=name, runtime=_lambda.Runtime.PYTHON_3_12, architecture=_lambda.Architecture.X86_64, handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(bundle(bundle_dir)), layers=[layer], memory_size=3008, timeout=Duration.seconds(60), environment=env, log_group=log_group,
            description="Whiteboard sketch objects on demand: one generated sheet -> cut, traced, gated drawings (docs/LIBRARY_ON_DEMAND.md part D)")
        # its only two rights: the gate's model, and the image provider's key (read at every call, never kept)
        self.fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:::foundation-model/*",
                                                                                                    f"arn:aws:bedrock:*:{self.account}:inference-profile/*"]))
        self.fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{OPENAI_SSM_PARAM}"]))
