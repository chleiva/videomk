"""videomk's own image catalog infrastructure (docs/IMAGE_CATALOG.md). Created ONLY with `-c imageCatalog=1` (default off: the stack is then exactly what it was).

A private bucket (originals, previews, thumbnails; immutable keys named by content hash), a metadata table, an S3 Vectors index `catalog-images` (Cohere Embed v4, 1024 d cosine) and the
demand table (generic search phrases only, a salted hash per video, expires after 12 months). The only runtime user is the beat Lambda, which may READ images and metadata, QUERY the
index and write one counter row per search; nothing else can reach them, nothing is public. Catalog images are expensive to make, so the data resources are retained on stack deletion.
"""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, aws_dynamodb as dynamodb, aws_iam as iam, aws_lambda as _lambda, aws_s3 as s3, aws_s3vectors as s3v
from constructs import Construct

SALT_PARAM = "/videomk/catalog_demand_salt"


class ImageCatalog(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, stage: str, account: str, region: str, is_prod: bool, beat_fn: _lambda.Function, min_score: str = "") -> None:
        super().__init__(scope, construct_id)
        bucket_name = f"videomk-{stage}-catalog-{account}"
        vector_bucket_name = f"videomk-{stage}-catalog-vec-{account}"
        table_name = f"videomk-{stage}-catalog-items"
        bucket = s3.Bucket(self, "CatalogBucket", bucket_name=bucket_name, block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
                           removal_policy=RemovalPolicy.RETAIN, object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, versioned=True,
                           lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(2), noncurrent_version_expiration=Duration.days(90))])
        items = dynamodb.Table(self, "CatalogTable", table_name=table_name, partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                               point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True), removal_policy=RemovalPolicy.RETAIN)
        demand = dynamodb.Table(self, "DemandTable", partition_key=dynamodb.Attribute(name="phrase", type=dynamodb.AttributeType.STRING), sort_key=dynamodb.Attribute(name="video", type=dynamodb.AttributeType.STRING),
                                billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires", removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY)
        vbucket = s3v.CfnVectorBucket(self, "CatalogVectorBucket", vector_bucket_name=vector_bucket_name)
        vindex = s3v.CfnIndex(self, "CatalogIndex", vector_bucket_name=vector_bucket_name, index_name="catalog-images", data_type="float32", dimension=1024, distance_metric="cosine")
        vindex.add_dependency(vbucket)
        vbucket.apply_removal_policy(RemovalPolicy.RETAIN)
        vindex.apply_removal_policy(RemovalPolicy.RETAIN)

        # the beat Lambda: read two prefixes (never o/ of anything else, never write), read one row by key, query one index, count a search, read one SSM parameter
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"{bucket.bucket_arn}/o/*", f"{bucket.bucket_arn}/p/*"]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[items.table_arn]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:UpdateItem"], resources=[demand.table_arn]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3vectors:QueryVectors", "s3vectors:GetVectors"], resources=[vindex.attr_index_arn]))
        beat_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter{SALT_PARAM}"]))
        for k, v in {"CATALOG_BUCKET": bucket_name, "CATALOG_TABLE": table_name, "CATALOG_VECTOR_BUCKET": vector_bucket_name, "CATALOG_VECTOR_INDEX": "catalog-images", "CATALOG_DEMAND_TABLE": demand.table_name,
                     "CATALOG_SALT_PARAM": SALT_PARAM, **({"CATALOG_MIN_SCORE": min_score} if min_score else {})}.items():
            beat_fn.add_environment(k, v)
        CfnOutput(self, "CatalogBucketName", value=bucket_name)
        CfnOutput(self, "CatalogVectorBucketName", value=vector_bucket_name)
        CfnOutput(self, "CatalogTableName", value=table_name)
        CfnOutput(self, "CatalogDemandTableName", value=demand.table_name)
        self.bucket, self.table, self.demand_table, self.vector_bucket_name, self.index_arn = bucket, items, demand, vector_bucket_name, vindex.attr_index_arn
