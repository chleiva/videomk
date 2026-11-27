"""CDK wiring of the sign-in branding: the pool domain on Managed Login (newer) and one branding per app client (web + mobile).

On by default; `-c loginBranding=0` leaves the classic hosted page. Needs the Essentials or Plus feature plan (both pools are on Essentials).
"""
from typing import Sequence

from aws_cdk import aws_cognito as cognito
from constructs import Construct

from . import assets, settings


def enabled(node) -> bool:
    return str(node.try_get_context("loginBranding") if node.try_get_context("loginBranding") is not None else "1").lower() not in ("0", "false", "off", "no")


def domain_version(node):
    return cognito.ManagedLoginVersion.NEWER_MANAGED_LOGIN if enabled(node) else None


def attach(scope: Construct, *, user_pool: cognito.IUserPool, clients: Sequence[cognito.UserPoolClient], domain: cognito.UserPoolDomain) -> list:
    """One CfnManagedLoginBranding per client (a client has at most one), created after the domain switched to Managed Login."""
    out = []
    if not enabled(scope.node):
        return out
    for i, client in enumerate(clients):
        b = cognito.CfnManagedLoginBranding(
            scope, f"LoginBranding{i}", user_pool_id=user_pool.user_pool_id, client_id=client.user_pool_client_id, use_cognito_provided_values=False, settings=settings(),
            assets=[cognito.CfnManagedLoginBranding.AssetTypeProperty(category=a["category"], color_mode=a["color_mode"], extension=a["extension"], bytes=a["bytes"]) for a in assets()],
        )
        b.node.add_dependency(domain)
        out.append(b)
    return out
