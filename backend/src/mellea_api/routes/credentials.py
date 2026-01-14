"""Credential management routes for secure secrets storage."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import CredentialType
from mellea_api.models.credential import (
    CredentialCreate,
    CredentialResponse,
    CredentialUpdate,
)
from mellea_api.services.credentials import (
    CredentialNotFoundError,
    CredentialService,
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
    """
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
