"""Engine v2 infrastructure: serverless-only (Lambda + Step Functions + S3), zero cost at idle.

  Plan ─ legit? ─ no ─▶ MarkRejected ─▶ Succeed
              └ yes ─▶ Beats (Map: TTS + photo scout) ─▶ Timeline ─▶ Parallel{ Chunks (Map: render ~30 s each) | Audio } ─▶ Finalize
Any failure ─▶ MarkFailed (refunds the quota) ─▶ Fail.
"""
from typing import Callable, Dict

from aws_cdk import Duration, aws_iam as iam, aws_lambda as _lambda, aws_stepfunctions as sfn, aws_stepfunctions_tasks as tasks
from constructs import Construct

TRANSIENT = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]


class EngineV2(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        make_fn: Callable[..., _lambda.Function],
        engine_layer: _lambda.ILayerVersion,
        videos_table,
        assets_bucket: str,
        mark_failed_fn: _lambda.IFunction,
        mark_rejected_fn: _lambda.IFunction,
        env: Dict[str, str],
        account: str,
        region: str,
        render_concurrency: int = 8,
        beat_concurrency: int = 5,
    ) -> None:
        super().__init__(scope, construct_id)
        layers = [engine_layer]
        base = "engine.handlers"
        v2_objects = f"arn:aws:s3:::{assets_bucket}/generation/v2/*"
        videos_objects = f"arn:aws:s3:::{assets_bucket}/videos/*"

        plan_fn = make_fn("V2PlanFn", "v2_plan", f"{base}.plan_handler.handler", timeout=Duration.minutes(5), memory=1024, env=env, layers=layers)
        beat_fn = make_fn("V2BeatFn", "v2_beat", f"{base}.beat_handler.handler", timeout=Duration.minutes(3), memory=1536, env=env, layers=layers)
        timeline_fn = make_fn("V2TimelineFn", "v2_timeline", f"{base}.timeline_handler.handler", timeout=Duration.seconds(60), memory=512, env=env, layers=layers)
        chunk_fn = make_fn("V2RenderChunkFn", "v2_render_chunk", f"{base}.render_chunk_handler.handler", timeout=Duration.minutes(10), memory=3008, env=env, layers=layers, ephemeral_mb=1024)
        audio_fn = make_fn("V2AudioFn", "v2_audio", f"{base}.audio_handler.handler", timeout=Duration.minutes(5), memory=3008, env=env, layers=layers, ephemeral_mb=2048)
        finalize_fn = make_fn("V2FinalizeFn", "v2_finalize", f"{base}.finalize_handler.handler", timeout=Duration.minutes(10), memory=3008, env=env, layers=layers, ephemeral_mb=4096)
        self.selftest_fn = make_fn("V2SelfTestFn", "engine_selftest", f"{base}.selftest_handler.handler", timeout=Duration.seconds(90), memory=3008, env=env, layers=layers)

        # --- least-privilege IAM: the engine can only touch generation/v2/* (+ write videos/*)
        for fn in (plan_fn, beat_fn, finalize_fn):
            videos_table.grant_read_write_data(fn)
        plan_fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:*:{account}:inference-profile/*"]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter/videomk/*_api_key"]))
        for fn in (plan_fn, beat_fn, timeline_fn):
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject"], resources=[v2_objects]))
        for fn in (chunk_fn, audio_fn):
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject"], resources=[v2_objects]))
        finalize_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[v2_objects]))
        finalize_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:PutObject"], resources=[videos_objects]))

        def invoke(cid: str, fn: _lambda.IFunction, **kw) -> tasks.LambdaInvoke:
            t = tasks.LambdaInvoke(self, cid, lambda_function=fn, payload_response_only=True, **kw)
            t.add_retry(errors=TRANSIENT, interval=Duration.seconds(2), max_attempts=3, backoff_rate=2.0)
            return t

        plan_t = invoke("V2Plan", plan_fn, result_path="$")
        beat_t = invoke("V2Beat", beat_fn, result_path="$")
        beat_t.add_retry(errors=["States.TaskFailed"], interval=Duration.seconds(4), max_attempts=3, backoff_rate=2.0)  # TTS/provider 429s
        beats_map = sfn.Map(
            self, "V2Beats", items_path="$.beat_indices", max_concurrency=beat_concurrency, result_path="$.beats",
            item_selector={"video_id.$": "$.video_id", "i.$": "$$.Map.Item.Value"},
        )
        beats_map.item_processor(beat_t)

        timeline_t = invoke("V2Timeline", timeline_fn, result_path="$")

        chunk_t = invoke("V2RenderChunk", chunk_fn)
        chunk_t.add_retry(errors=["States.TaskFailed"], interval=Duration.seconds(3), max_attempts=2, backoff_rate=2.0)
        chunks_map = sfn.Map(self, "V2Chunks", items_path="$.chunks", max_concurrency=render_concurrency)
        chunks_map.item_processor(chunk_t)
        audio_t = tasks.LambdaInvoke(
            self, "V2Audio", lambda_function=audio_fn, payload_response_only=True,
            payload=sfn.TaskInput.from_object({"video_id.$": "$.video_id", "timeline_key.$": "$.timeline_key"}),
        )
        audio_t.add_retry(errors=TRANSIENT + ["States.TaskFailed"], interval=Duration.seconds(3), max_attempts=2, backoff_rate=2.0)
        render = sfn.Parallel(self, "V2Render", result_path="$.render", result_selector={"segments.$": "$[0]", "audio.$": "$[1]"})
        render.branch(chunks_map)
        render.branch(audio_t)

        finalize_t = invoke("V2Finalize", finalize_fn, result_path="$")

        mark_failed = tasks.LambdaInvoke(self, "V2MarkFailed", lambda_function=mark_failed_fn, payload_response_only=True, result_path="$.error_result")
        failure = sfn.Chain.start(mark_failed).next(sfn.Fail(self, "V2Failed"))
        for t in (plan_t, beats_map, timeline_t, render, finalize_t):
            t.add_catch(failure, errors=["States.ALL"], result_path="$.error")

        mark_rejected = tasks.LambdaInvoke(self, "V2MarkRejected", lambda_function=mark_rejected_fn, payload_response_only=True, result_path="$.rejected")
        mark_rejected.add_catch(failure, errors=["States.ALL"], result_path="$.error")
        rejected = sfn.Chain.start(mark_rejected).next(sfn.Succeed(self, "V2Rejected"))

        legit = sfn.Choice(self, "V2PromptLegit?")
        legit.when(sfn.Condition.boolean_equals("$.plot.legit", True), beats_map).otherwise(rejected)
        beats_map.next(timeline_t).next(render).next(finalize_t)

        self.state_machine = sfn.StateMachine(
            self, "GenerateVideoWorkflowV2",
            state_machine_name="generate_video_workflow_v2",
            definition_body=sfn.DefinitionBody.from_chainable(sfn.Chain.start(plan_t).next(legit)),
            timeout=Duration.minutes(45),
        )
