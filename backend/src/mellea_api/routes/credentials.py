"""Credential management routes for secure secrets storage."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import AccessType, CredentialType
from mellea_api.models.credential import (
    CredentialCreate,
    CredentialResponse,
    CredentialSharedAccessResponse,
    CredentialUpdate,
    ShareCredentialRequest,
    ShareCredentialResponse,
)
from mellea_api.services.credentials import (
    CredentialNotFoundError,
    CredentialService,
    CredentialValidationError,
    get_credential_service,
)

CredentialServiceDep = Annotated[CredentialService, Depends(get_credential_service)]

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    credential_data: CredentialCreate,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> CredentialResponse:
    """Create a new credential.

    Securely stores the provided secret data with encryption at rest.
    The secret data is never returned in API responses.

    Validates secret_data against provider-specific requirements:
    - OpenAI: requires api_key, optional organization_id
    - Anthropic: requires api_key
    - Azure: requires (api_key + endpoint) or (tenant_id + client_id + client_secret + endpoint)
    - Ollama: optional api_key
    - Custom: no validation
    """
    try:
        credential = credential_service.create_credential(
            name=credential_data.name,
            credential_type=credential_data.type,
            secret_data=credential_data.secret_data,
            provider=credential_data.provider,
            owner_id=current_user.id,
            description=credential_data.description,
            tags=credential_data.tags,
            expires_at=credential_data.expires_at,
        )
    except CredentialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.message,
                "missing_keys": e.missing_keys,
            },
        ) from e

    return CredentialResponse.from_credential(credential)


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
    credential_type: CredentialType | None = Query(
        None, alias="type", description="Filter by credential type"
    ),
    provider: str | None = Query(None, description="Filter by provider"),
) -> list[CredentialResponse]:
    """List credentials owned by the current user.

    Returns credential metadata without secret values.
    """
    credentials = credential_service.list_credentials(
        owner_id=current_user.id,
        credential_type=credential_type,
        provider=provider,
    )

    return [CredentialResponse.from_credential(c) for c in credentials]


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: str,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> CredentialResponse:
    """Get credential metadata by ID.

    Returns metadata only, not the secret values.
    Use the /secret endpoint to retrieve actual secret data.
    """
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    # Check ownership
    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this credential",
        )

    return CredentialResponse.from_credential(credential)


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: str,
    updates: CredentialUpdate,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> CredentialResponse:
    """Update a credential.

    Can update metadata and/or rotate the secret data.
    When updating secret_data, validates against provider-specific requirements.
    """
    # Check existence and ownership first
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this credential",
        )

    try:
        updated = credential_service.update_credential(
            credential_id=credential_id,
            name=updates.name,
            description=updates.description,
            secret_data=updates.secret_data,
            tags=updates.tags,
            expires_at=updates.expires_at,
        )
        return CredentialResponse.from_credential(updated)
    except CredentialNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except CredentialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.message,
                "missing_keys": e.missing_keys,
            },
        ) from e


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: str,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> None:
    """Delete a credential.

    Permanently removes the credential and its encrypted secret data.
    """
    # Check existence and ownership first
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this credential",
        )

    credential_service.delete_credential(credential_id)


@router.post("/{credential_id}/validate")
async def validate_credential(
    credential_id: str,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> dict[str, bool]:
    """Validate a credential.

    Checks if the credential exists and is not expired.
    """
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to validate this credential",
        )

    is_valid = credential_service.validate_credential(credential_id)

    return {"valid": is_valid, "expired": credential.is_expired}


@router.get("/accessible", response_model=list[CredentialResponse])
async def list_accessible_credentials(
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
    credential_type: CredentialType | None = Query(
        None, alias="type", description="Filter by credential type"
    ),
    provider: str | None = Query(None, description="Filter by provider"),
) -> list[CredentialResponse]:
    """List credentials accessible to the current user (owned or shared).

    Returns credentials the user owns or has been granted access to.
    """
    credentials = credential_service.list_accessible_credentials(
        user_id=current_user.id,
        credential_type=credential_type,
        provider=provider,
    )

    return [CredentialResponse.from_credential(c) for c in credentials]


@router.post(
    "/{credential_id}/share",
    response_model=ShareCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def share_credential(
    credential_id: str,
    share_request: ShareCredentialRequest,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> ShareCredentialResponse:
    """Share a credential with another user.

    Only the credential owner can share it. The shared user will be able
    to use the credential in their runs depending on the permission level:
    - VIEW: Can see credential metadata but not use in runs
    - RUN: Can use the credential in program runs
    - EDIT: Can use and manage sharing (not recommended for credentials)
    """
    # Check existence and ownership
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the credential owner can share it",
        )

    # Cannot share with yourself
    if share_request.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a credential with yourself",
        )

    try:
        updated_credential = credential_service.share_credential(
            credential_id=credential_id,
            user_id=share_request.user_id,
            permission=share_request.permission,
            shared_by=current_user.id,
        )
    except CredentialNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    # Find the newly added/updated share entry
    from datetime import datetime

    for access in updated_credential.shared_with:
        if access.type == AccessType.USER and access.id == share_request.user_id:
            return ShareCredentialResponse(
                credentialId=credential_id,
                userId=share_request.user_id,
                permission=access.permission,
                sharedAt=access.shared_at,
                sharedBy=access.shared_by,
            )

    # Should never reach here, but provide a fallback response
    return ShareCredentialResponse(
        credentialId=credential_id,
        userId=share_request.user_id,
        permission=share_request.permission,
        sharedAt=datetime.utcnow(),
        sharedBy=current_user.id,
    )


@router.get(
    "/{credential_id}/shared-with",
    response_model=list[CredentialSharedAccessResponse],
)
async def list_credential_shares(
    credential_id: str,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> list[CredentialSharedAccessResponse]:
    """List users who have been shared access to this credential.

    Only the credential owner can see who has access.
    """
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the credential owner can view sharing info",
        )

    return [
        CredentialSharedAccessResponse(
            type=access.type,
            id=access.id,
            permission=access.permission,
            sharedAt=access.shared_at,
            sharedBy=access.shared_by,
        )
        for access in credential.shared_with
    ]


@router.delete(
    "/{credential_id}/shared-with/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_credential_share(
    credential_id: str,
    user_id: str,
    current_user: CurrentUser,
    credential_service: CredentialServiceDep,
) -> None:
    """Revoke a user's access to a credential.

    Only the credential owner can revoke access.
    """
    credential = credential_service.get_credential(credential_id)

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential not found: {credential_id}",
        )

    if credential.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the credential owner can revoke access",
        )

    try:
        credential_service.revoke_credential_share(
            credential_id=credential_id,
            user_id=user_id,
        )
    except CredentialNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
