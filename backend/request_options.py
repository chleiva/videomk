"""The creation options: GET /users/{user}/capabilities and the server settings that decide which formats and languages are ready (docs/CREATE_OPTIONS_FLOW.md).

One small Lambda with no data access and no IAM beyond logging. The same settings are given to the launcher, which refuses a format that is not ready.
Switch a format on with a stack context key, e.g. `-c readyAspects=16:9,9:16 -c betaAspects=9:16`; nothing else changes.
4K is switched on the same way: `-c readyResolutions=720p,1080p,2160p` (default `720p,1080p`, i.e. no 4K), see docs/FOUR_K.md.
"""
from typing import Callable, Dict

from aws_cdk import Duration, aws_apigateway as apigw, aws_lambda as _lambda
from constructs import Construct


class RequestOptions(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, make_fn: Callable[..., _lambda.Function], user_id_resource: apigw.IResource, cognito_auth: Dict, launcher_fn: _lambda.Function,
        ready_aspects: str = "16:9", beta_aspects: str = "", ready_languages: str = "en,es", intake_enabled: bool = False, ready_resolutions: str = "720p,1080p",
    ) -> None:
        super().__init__(scope, construct_id)
        settings = {"READY_ASPECTS": ready_aspects, "BETA_ASPECTS": beta_aspects, "READY_LANGUAGES": ready_languages, "READY_RESOLUTIONS": ready_resolutions}
        self.fn = make_fn("CapabilitiesFunction", "capabilities_api", "capabilities_api.handler", timeout=Duration.seconds(5), env={**settings, "INTAKE_ENABLED": "1" if intake_enabled else "0"})
        for k, v in settings.items():
            launcher_fn.add_environment(k, v)   # the launcher refuses what capabilities does not list as ready
        res = user_id_resource.add_resource("capabilities")
        res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["GET", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "X-Region", "X-Timezone"])
        res.add_method("GET", apigw.LambdaIntegration(self.fn, proxy=True), **cognito_auth)
