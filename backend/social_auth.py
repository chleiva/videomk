"""Sign in with Google / Apple through Cognito federation (docs/AUTH_SOCIAL.md).

Everything is behind CDK context flags that default OFF (`-c socialGoogle=1`, `-c socialApple=1`), so the stack deploys with no secrets today.
Credentials are never in code, cdk.json or stages.json: the template holds dynamic references, CloudFormation reads the values at deploy time.
  plain ids   -> SSM String parameters      /videomk/google_oauth_client_id, /videomk/apple_services_id, /videomk/apple_team_id, /videomk/apple_key_id
  secrets     -> Secrets Manager (plain-text) /videomk/google_oauth_client_secret, /videomk/apple_private_key (the .p8 file contents)
(`{{resolve:ssm-secure:..}}` is not accepted by the Cognito identity provider resource, so the two real secrets live in Secrets Manager.)
"""
import os
from typing import Any, Dict, List

from aws_cdk import (
    CfnDynamicReference,
    CfnDynamicReferenceService,
    CfnOutput,
    Duration,
    SecretValue,
    Stack,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
)
from constructs import Construct

GOOGLE_PARAMS = {"client_id": "/videomk/google_oauth_client_id"}
GOOGLE_SECRETS = {"client_secret": "/videomk/google_oauth_client_secret"}
APPLE_PARAMS = {"services_id": "/videomk/apple_services_id", "team_id": "/videomk/apple_team_id", "key_id": "/videomk/apple_key_id"}
APPLE_SECRETS = {"private_key": "/videomk/apple_private_key"}


def flag(node, name: str) -> bool:
    v = node.try_get_context(name)
    return str(v).strip().lower() in ("1", "true", "yes", "on") if v is not None else False


def required_names(google: bool, apple: bool) -> Dict[str, List[str]]:
    """The SSM parameter names and Secrets Manager secret names that must exist for the enabled providers."""
    ssm = (list(GOOGLE_PARAMS.values()) if google else []) + (list(APPLE_PARAMS.values()) if apple else [])
    sec = (list(GOOGLE_SECRETS.values()) if google else []) + (list(APPLE_SECRETS.values()) if apple else [])
    return {"ssm": ssm, "secrets": sec}


def missing_values(session, google: bool, apple: bool) -> List[str]:
    """Names that do not exist (or cannot be read) in the account of `session`. Used by app.py before synthesis so a flag with no value fails early and clearly."""
    need = required_names(google, apple)
    missing: List[str] = []
    ssm, sm = session.client("ssm"), session.client("secretsmanager")
    for n in need["ssm"]:
        try:
            if not ssm.get_parameter(Name=n)["Parameter"]["Value"].strip():
                missing.append(f"SSM parameter {n} (empty)")
        except Exception as e:  # noqa: BLE001
            missing.append(f"SSM parameter {n} ({type(e).__name__})")
    for n in need["secrets"]:
        try:
            if not sm.describe_secret(SecretId=n):
                missing.append(f"Secrets Manager secret {n}")
        except Exception as e:  # noqa: BLE001
            missing.append(f"Secrets Manager secret {n} ({type(e).__name__})")
    return missing


def _ssm(name: str) -> str:
    return CfnDynamicReference(CfnDynamicReferenceService.SSM, name).to_string()


def _secret(name: str) -> SecretValue:
    return SecretValue.secrets_manager(name)


class SocialAuth(Construct):
    """Identity providers, the account-linking trigger and the outputs. `clients` are given later through `attach_clients` (they must exist after the providers)."""

    def __init__(self, scope: Construct, cid: str, *, user_pool: cognito.UserPool, hosted_ui: cognito.UserPoolDomain, google: bool, apple: bool, make_fn) -> None:
        super().__init__(scope, cid)
        self.google, self.apple = google, apple
        self.providers: List[cognito.UserPoolIdentityProvider] = []
        self.client_idps: List[cognito.UserPoolClientIdentityProvider] = []
        if google:
            self.providers.append(cognito.UserPoolIdentityProviderGoogle(
                self, "Google", user_pool=user_pool, client_id=_ssm(GOOGLE_PARAMS["client_id"]), client_secret_value=_secret(GOOGLE_SECRETS["client_secret"]),
                scopes=["openid", "email", "profile"],
                attribute_mapping=cognito.AttributeMapping(
                    email=cognito.ProviderAttribute.GOOGLE_EMAIL, given_name=cognito.ProviderAttribute.GOOGLE_GIVEN_NAME,
                    family_name=cognito.ProviderAttribute.GOOGLE_FAMILY_NAME, fullname=cognito.ProviderAttribute.GOOGLE_NAME,
                    custom={"email_verified": cognito.ProviderAttribute.GOOGLE_EMAIL_VERIFIED}),
            ))
            self.client_idps.append(cognito.UserPoolClientIdentityProvider.GOOGLE)
        if apple:
            self.providers.append(cognito.UserPoolIdentityProviderApple(
                self, "Apple", user_pool=user_pool, client_id=_ssm(APPLE_PARAMS["services_id"]), team_id=_ssm(APPLE_PARAMS["team_id"]), key_id=_ssm(APPLE_PARAMS["key_id"]),
                private_key_value=_secret(APPLE_SECRETS["private_key"]), scopes=["name", "email"],
                attribute_mapping=cognito.AttributeMapping(
                    email=cognito.ProviderAttribute.APPLE_EMAIL, given_name=cognito.ProviderAttribute.APPLE_FIRST_NAME, family_name=cognito.ProviderAttribute.APPLE_LAST_NAME),
            ))
            self.client_idps.append(cognito.UserPoolClientIdentityProvider.APPLE)
        if google or apple:
            fn = make_fn("AuthPreSignUpFunction", "auth_presignup", "auth_presignup.handler", timeout=Duration.seconds(10))
            user_pool.add_trigger(cognito.UserPoolOperation.PRE_SIGN_UP, fn)
            # Least privilege, in a separate policy resource (the pool references the function, so the function's role cannot reference the pool without a cycle).
            iam.Policy(self, "PreSignUpPolicy", roles=[fn.role], statements=[iam.PolicyStatement(
                actions=["cognito-idp:ListUsers", "cognito-idp:AdminLinkProviderForUser"], resources=[user_pool.user_pool_arn])])
            self.trigger = fn
        enabled = [n for n, on in (("Google", google), ("SignInWithApple", apple)) if on]
        uri = f"{hosted_ui.base_url()}/oauth2/idpresponse"
        CfnOutput(Stack.of(self), "SocialProviders", value=",".join(enabled) or "none", description="Federated identity providers enabled on the user pool")
        CfnOutput(Stack.of(self), "SocialRedirectUri", value=uri, description="Register this exact URL at Google (authorised redirect URI) and Apple (Services ID return URL)")
        CfnOutput(Stack.of(self), "SocialAppleDomain", value=hosted_ui.base_url().replace("https://", ""), description="Apple Services ID: Domain (the Cognito domain, no scheme)")

    def attach_clients(self, *clients: cognito.UserPoolClient) -> None:
        for c in clients:
            for p in self.providers:
                c.node.add_dependency(p)
