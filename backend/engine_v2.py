"""Engine v2 infrastructure: serverless-only (Lambda + Step Functions + S3), zero cost at idle.

generate:  Plan ─ legit? ─ no ─▶ MarkRejected ─▶ Succeed
                     └ yes ─▶ TAIL
edit:      EditPrep (which beats changed?) ─▶ TAIL
TAIL:      Beats (Map: TTS + photo scout, only what changed) ─▶ Timeline ─▶ Parallel{ Chunks (Map: ~30 s each, cached by content hash) | Audio } ─▶ Finalize
Any generate failure ─▶ MarkFailed (refunds the quota) ─▶ Fail.   Any edit failure ─▶ EditFailed (the video stays playable) ─▶ Fail.
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
        usage_table,
        env: Dict[str, str],
        account: str,
        region: str,
        render_concurrency: int = 32,
        beat_concurrency: int = 12,
    ) -> None:
        super().__init__(scope, construct_id)
        layers = [engine_layer]
        base = "engine.handlers"
        v2_objects = f"arn:aws:s3:::{assets_bucket}/generation/v2/*"
        videos_objects = f"arn:aws:s3:::{assets_bucket}/videos/*"

        plan_fn = make_fn("V2PlanFn", "v2_plan", f"{base}.plan_handler.handler", timeout=Duration.minutes(10), memory=1024, env=env, layers=layers)   # long videos: an outline, then sections with their own research, in parallel
        beat_fn = make_fn("V2BeatFn", "v2_beat", f"{base}.beat_handler.handler", timeout=Duration.minutes(3), memory=1536, env=env, layers=layers)
        timeline_fn = make_fn("V2TimelineFn", "v2_timeline", f"{base}.timeline_handler.handler", timeout=Duration.seconds(60), memory=512, env=env, layers=layers)
        chunk_fn = make_fn("V2RenderChunkFn", "v2_render_chunk", f"{base}.render_chunk_handler.handler", timeout=Duration.minutes(10), memory=3008, env=env, layers=layers, ephemeral_mb=1024)
        audio_fn = make_fn("V2AudioFn", "v2_audio", f"{base}.audio_handler.handler", timeout=Duration.minutes(5), memory=3008, env=env, layers=layers, ephemeral_mb=2048)
        finalize_fn = make_fn("V2FinalizeFn", "v2_finalize", f"{base}.finalize_handler.handler", timeout=Duration.minutes(10), memory=3008, env=env, layers=layers, ephemeral_mb=4096)
        edit_prep_fn = make_fn("V2EditPrepFn", "v2_edit_prep", f"{base}.edit_prep_handler.handler", timeout=Duration.seconds(30), memory=512, env=env, layers=layers)
        edit_failed_fn = make_fn("V2EditFailedFn", "v2_edit_failed", f"{base}.edit_failed_handler.handler", timeout=Duration.seconds(10), memory=256, env=env, layers=layers)
        self.editor_get_fn = make_fn("V2EditorGetFn", "v2_editor_get", f"{base}.editor_get.handler", timeout=Duration.seconds(20), memory=512, env=env, layers=layers)
        self.editor_apply_fn = make_fn("V2EditorApplyFn", "v2_editor_apply", f"{base}.editor_apply.handler", timeout=Duration.seconds(20), memory=512, env=env, layers=layers)
        self.selftest_fn = make_fn("V2SelfTestFn", "engine_selftest", f"{base}.selftest_handler.handler", timeout=Duration.seconds(90), memory=3008, env=env, layers=layers)

        # --- least-privilege IAM: the engine can only touch generation/v2/* (+ write videos/*)
        for fn in (plan_fn, beat_fn, finalize_fn):
            videos_table.grant_read_write_data(fn)
        for fn in (plan_fn, beat_fn):  # the beat Lambda runs the vision photo review
            fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:*:{account}:inference-profile/*"]))
        plan_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter/videomk/tavily_api_key"]))
        # the user's uploaded photos: read, then delete once the clean copy exists (the clean copy goes under generation/v2/, already allowed above)
        plan_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:DeleteObject"], resources=[f"arn:aws:s3:::{assets_bucket}/uploads/*"]))
        for fn in (plan_fn, audio_fn, self.editor_get_fn):  # the curated music library: the planner reads the catalogue, the audio step the tracks
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"arn:aws:s3:::{assets_bucket}/music/*"]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["polly:SynthesizeSpeech"], resources=["*"]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter/videomk/*_api_key", f"arn:aws:ssm:{region}:{account}:parameter/videomk/unsplash_access_key"]))
        for fn in (plan_fn, beat_fn, timeline_fn):
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject"], resources=[v2_objects]))
        for fn in (chunk_fn, audio_fn, beat_fn):  # they write segments, mixes and stock clips, which carry the "working" tag
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:PutObjectTagging"], resources=[v2_objects]))
        finalize_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[v2_objects]))
        finalize_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:PutObject"], resources=[videos_objects]))

        # HeadObject (the content-addressed cache lookups) answers 403 instead of 404 for a missing key unless the role may
        # list the prefix: grant exactly that, no more.
        for fn in (beat_fn, chunk_fn):
            fn.add_to_role_policy(iam.PolicyStatement(
                actions=["s3:ListBucket"], resources=[f"arn:aws:s3:::{assets_bucket}"],
                conditions={"StringLike": {"s3:prefix": ["generation/v2/*"]}},
            ))
        edit_prep_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[v2_objects]))
        videos_table.grant_read_write_data(edit_failed_fn)
        videos_table.grant_read_data(self.editor_get_fn)
        videos_table.grant_read_write_data(self.editor_apply_fn)
        usage_table.grant_read_write_data(self.editor_apply_fn)
        self.editor_get_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:GetBucketLocation"], resources=[v2_objects, videos_objects, f"arn:aws:s3:::{assets_bucket}"]))
        self.editor_apply_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject"], resources=[v2_objects]))

        def invoke(cid: str, fn: _lambda.IFunction, **kw) -> tasks.LambdaInvoke:
            t = tasks.LambdaInvoke(self, cid, lambda_function=fn, payload_response_only=True, **kw)
            t.add_retry(errors=TRANSIENT, interval=Duration.seconds(2), max_attempts=3, backoff_rate=2.0)
            return t

        def tail(p: str, failure: sfn.IChainable):
            """Beats -> Timeline -> Parallel{Chunks, Audio} -> Finalize. Returns (first, last); state objects can't be shared across machines."""
            beat_t = invoke(f"{p}Beat", beat_fn, result_path="$")
            beat_t.add_retry(errors=["States.TaskFailed"], interval=Duration.seconds(4), max_attempts=3, backoff_rate=2.0)  # TTS/provider 429s
            beats_map = sfn.Map(
                self, f"{p}Beats", items_path="$.beat_ids", max_concurrency=beat_concurrency, result_path="$.beats",
                item_selector={"video_id.$": "$.video_id", "plan_key.$": "$.plan_key", "cost_field.$": "$.cost_field", "beat_id.$": "$$.Map.Item.Value"},
            )
            beats_map.item_processor(beat_t)
            timeline_t = invoke(f"{p}Timeline", timeline_fn, result_path="$")
            chunk_t = invoke(f"{p}RenderChunk", chunk_fn)
            chunk_t.add_retry(errors=["States.TaskFailed"], interval=Duration.seconds(3), max_attempts=2, backoff_rate=2.0)
            chunks_map = sfn.Map(self, f"{p}Chunks", items_path="$.chunks", max_concurrency=render_concurrency)
            chunks_map.item_processor(chunk_t)
            audio_t = tasks.LambdaInvoke(
                self, f"{p}Audio", lambda_function=audio_fn, payload_response_only=True,
                payload=sfn.TaskInput.from_object({"video_id.$": "$.video_id", "timeline_key.$": "$.timeline_key", "rev.$": "$.rev", "mode.$": "$.mode"}),
            )
            audio_t.add_retry(errors=TRANSIENT + ["States.TaskFailed"], interval=Duration.seconds(3), max_attempts=2, backoff_rate=2.0)
            render = sfn.Parallel(self, f"{p}Render", result_path="$.render", result_selector={"segments.$": "$[0]", "audio.$": "$[1]"})
            render.branch(chunks_map)
            render.branch(audio_t)
            finalize_t = invoke(f"{p}Finalize", finalize_fn, result_path="$")
            for t in (beats_map, timeline_t, render, finalize_t):
                t.add_catch(failure, errors=["States.ALL"], result_path="$.error")
            beats_map.next(timeline_t).next(render).next(finalize_t)
            return beats_map, finalize_t

        # ---- generate
        mark_failed = tasks.LambdaInvoke(self, "V2MarkFailed", lambda_function=mark_failed_fn, payload_response_only=True, result_path="$.error_result")
        failure = sfn.Chain.start(mark_failed).next(sfn.Fail(self, "V2Failed"))
        plan_t = invoke("V2Plan", plan_fn, result_path="$")
        plan_t.add_catch(failure, errors=["States.ALL"], result_path="$.error")
        first, _ = tail("V2", failure)
        mark_rejected = tasks.LambdaInvoke(self, "V2MarkRejected", lambda_function=mark_rejected_fn, payload_response_only=True, result_path="$.rejected")
        mark_rejected.add_catch(failure, errors=["States.ALL"], result_path="$.error")
        rejected = sfn.Chain.start(mark_rejected).next(sfn.Succeed(self, "V2Rejected"))
        legit = sfn.Choice(self, "V2PromptLegit?")
        legit.when(sfn.Condition.boolean_equals("$.plot.legit", True), first).otherwise(rejected)
        self.state_machine = sfn.StateMachine(
            self, "GenerateVideoWorkflowV2", state_machine_name="generate_video_workflow_v2",
            definition_body=sfn.DefinitionBody.from_chainable(sfn.Chain.start(plan_t).next(legit)), timeout=Duration.minutes(45),
        )

        # ---- edit (same tail; a failed edit never touches the video's own status)
        edit_failed = tasks.LambdaInvoke(self, "EditFailedMark", lambda_function=edit_failed_fn, payload_response_only=True, result_path="$.error_result")
        edit_failure = sfn.Chain.start(edit_failed).next(sfn.Fail(self, "EditFailed"))
        prep_t = invoke("EditPrep", edit_prep_fn, result_path="$")
        prep_t.add_catch(edit_failure, errors=["States.ALL"], result_path="$.error")
        efirst, _ = tail("Edit", edit_failure)
        self.edit_state_machine = sfn.StateMachine(
            self, "EditVideoWorkflowV2", state_machine_name="edit_video_workflow_v2",
            definition_body=sfn.DefinitionBody.from_chainable(sfn.Chain.start(prep_t).next(efirst)), timeout=Duration.minutes(45),
        )
        self.edit_state_machine.grant_start_execution(self.editor_apply_fn)
        self.editor_apply_fn.add_environment("EDIT_STATE_MACHINE_ARN", self.edit_state_machine.state_machine_arn)
