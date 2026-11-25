"""The private photo library infrastructure (docs/MEDIA_LIBRARY.md): a private bucket, a metadata table, an S3 Vectors index, an ingest queue and the API routes.

Least privilege: the API function can only presign and delete inside this bucket and query this index; the ingest function can read originals and write thumbnails
and vectors; the video launcher can only READ originals (to copy the photos a person chose into their own video). Nothing else touches the bucket.
"""
from typing import Callable, Dict

from aws_cdk import CfnOutput, Duration, RemovalPolicy, aws_apigateway as apigw, aws_dynamodb as dynamodb, aws_events as events, aws_events_targets as event_targets
from aws_cdk import aws_iam as iam, aws_lambda as _lambda, aws_lambda_event_sources as sources, aws_s3 as s3, aws_s3_notifications as s3n, aws_s3vectors as s3v, aws_sqs as sqs
from constructs import Construct


class MediaLibrary(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, stage: str, account: str, region: str, is_prod: bool, make_fn: Callable[..., _lambda.Function], engine_layer: _lambda.ILayerVersion,
        flags_table: dynamodb.ITable, usage_table: dynamodb.ITable, user_id_resource: apigw.IResource, cognito_auth: Dict, launcher_fn: _lambda.Function, assets_bucket_name: str,
    ) -> None:
        super().__init__(scope, construct_id)
        keep = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        media_bucket_name = f"videomk-{stage}-media-{account}"
        vector_bucket_name = f"videomk-{stage}-vec-{account}"

        bucket = s3.Bucket(
            self, "MediaBucket", bucket_name=media_bucket_name, block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
            removal_policy=keep, auto_delete_objects=not is_prod, object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(2))],   # originals are uploaded straight into Intelligent-Tiering (the presigned POST sets it)
        )
        table = dynamodb.Table(
            self, "MediaTable", partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING), sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=is_prod), removal_policy=keep,
        )
        table.add_global_secondary_index(index_name="Timeline", partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
                                         sort_key=dynamodb.Attribute(name="srt", type=dynamodb.AttributeType.STRING), projection_type=dynamodb.ProjectionType.ALL)
        table.add_global_secondary_index(index_name="Pending", partition_key=dynamodb.Attribute(name="pend", type=dynamodb.AttributeType.STRING),
                                         sort_key=dynamodb.Attribute(name="created", type=dynamodb.AttributeType.STRING), projection_type=dynamodb.ProjectionType.ALL)

        vbucket = s3v.CfnVectorBucket(self, "VectorBucket", vector_bucket_name=vector_bucket_name)
        vindex = s3v.CfnIndex(self, "PhotoIndex", vector_bucket_name=vector_bucket_name, index_name="photos", data_type="float32", dimension=1024, distance_metric="cosine")
        vindex.add_dependency(vbucket)
        if is_prod:
            vbucket.apply_removal_policy(RemovalPolicy.RETAIN)
            vindex.apply_removal_policy(RemovalPolicy.RETAIN)

        dlq = sqs.Queue(self, "IngestDlq", retention_period=Duration.days(14), encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True)
        queue = sqs.Queue(self, "IngestQueue", visibility_timeout=Duration.minutes(4), encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True,
                          dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=6, queue=dlq))
        bucket.add_event_notification(s3.EventType.OBJECT_CREATED, s3n.SqsDestination(queue), s3.NotificationKeyFilter(prefix="o/"))   # only originals (thumbnails are under t/)

        env = {"MEDIA_TABLE": table.table_name, "MEDIA_BUCKET": media_bucket_name, "VECTOR_BUCKET": vector_bucket_name, "VECTOR_INDEX": "photos", "LIBRARY_CAN_UPGRADE": "0", "INGEST_FINAL_ATTEMPT": "5"}
        api_fn = make_fn("LibraryApiFn", "library_api", "library_api.handler", timeout=Duration.seconds(30), memory=3008, env=env, layers=[engine_layer])
        ingest_fn = make_fn("LibraryIngestFn", "library_ingest", "library_ingest.handler", timeout=Duration.minutes(2), memory=3008, env=env, layers=[engine_layer])
        sweeper_fn = make_fn("LibrarySweeperFn", "library_sweeper", "library_sweeper.handler", timeout=Duration.minutes(5), memory=3008, env=env, layers=[engine_layer])
        ingest_fn.add_event_source(sources.SqsEventSource(queue, batch_size=5, max_concurrency=4 if is_prod else 6, report_batch_item_failures=True))
        events.Rule(self, "SweeperSchedule", schedule=events.Schedule.rate(Duration.hours(1)), targets=[event_targets.LambdaFunction(sweeper_fn)])

        originals, thumbs = f"{bucket.bucket_arn}/o/*", f"{bucket.bucket_arn}/t/*"
        def allow(fn, actions, resources):
            fn.add_to_role_policy(iam.PolicyStatement(actions=actions, resources=resources))

        index_arn = vindex.attr_index_arn
        embed_model = ["arn:aws:bedrock:*::foundation-model/cohere.embed-v4:0", f"arn:aws:bedrock:*:{account}:inference-profile/*.cohere.embed-v4:0"]   # Cohere Embed v4 through the regional profile
        for fn in (api_fn, ingest_fn, sweeper_fn):
            table.grant_read_write_data(fn)
        usage_table.grant_read_write_data(api_fn)
        flags_table.grant_read_data(api_fn)   # read only: nothing at runtime can grant itself storage
        flags_table.grant_read_data(ingest_fn)
        allow(api_fn, ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"], [originals, thumbs])    # presigned uploads and links are signed with this role; it never reads another prefix
        allow(api_fn, ["s3:ListBucket"], [bucket.bucket_arn])    # only for 'delete everything' (prefix o/<user>/ and t/<user>/)
        allow(api_fn, ["s3vectors:QueryVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors"], [index_arn])
        allow(api_fn, ["bedrock:InvokeModel"], embed_model + ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:*:{account}:inference-profile/*"])
        for fn in (ingest_fn, sweeper_fn):
            allow(fn, ["s3:GetObject", "s3:DeleteObject"], [originals])
            allow(fn, ["s3:PutObject", "s3:DeleteObject"], [thumbs])
            allow(fn, ["s3vectors:PutVectors", "s3vectors:DeleteVectors"], [index_arn])
            allow(fn, ["bedrock:InvokeModel"], embed_model)
        allow(sweeper_fn, ["s3:ListBucket"], [bucket.bucket_arn])    # head_object on a missing key answers 404 instead of 403 only with list rights
        # the video launcher: read one library photo and copy it into the video's own uploads; nothing else
        table.grant_read_data(launcher_fn)
        allow(launcher_fn, ["s3:GetObject", "s3:GetObjectTagging"], [originals])
        allow(launcher_fn, ["s3:PutObject"], [f"arn:aws:s3:::{assets_bucket_name}/uploads/*"])
        launcher_fn.add_environment("MEDIA_TABLE", table.table_name)
        launcher_fn.add_environment("MEDIA_BUCKET", media_bucket_name)

        # ---- routes
        lib = user_id_resource.add_resource("library")
        integration = apigw.LambdaIntegration(api_fn, proxy=True)
        def route(res: apigw.IResource, *methods: str) -> apigw.IResource:
            for m in methods:
                res.add_method(m, integration, **cognito_auth)
            return res

        route(lib.add_resource("summary"), "GET")
        route(lib.add_resource("uploads"), "POST")
        items = route(lib.add_resource("items"), "GET")
        route(items.add_resource("delete"), "POST")
        route(items.add_resource("{item_id}"), "GET")
        route(lib.add_resource("search"), "POST")
        route(lib.add_resource("delete-all"), "POST")
        cols = route(lib.add_resource("collections"), "GET", "POST")
        col = route(cols.add_resource("{collection_id}"), "POST")
        route(col.add_resource("delete"), "POST")
        route(col.add_resource("items"), "POST")

        CfnOutput(self, "MediaBucketName", value=media_bucket_name)
        CfnOutput(self, "VectorBucketName", value=vector_bucket_name)
        self.table, self.bucket, self.api_fn, self.ingest_fn = table, bucket, api_fn, ingest_fn
