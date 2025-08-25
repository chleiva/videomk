from typing import Optional


def validate_user_id(user_id: Optional[str]) -> None:
    """
    Placeholder for Cognito validation.
    In a future iteration, decode/verify the caller's identity and ensure the provided
    user_id matches the authenticated subject.
    """
    if not user_id:
        raise ValueError("user_id is required")
    # TODO: Implement Cognito User Pool validation


