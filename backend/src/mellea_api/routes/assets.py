"""Asset routes for creating and retrieving catalog assets."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.assets import (
    CompositionAsset,
    ModelAsset,
    ProgramAsset,
)
from mellea_api.services.assets import (
    AssetAlreadyExistsError,
    AssetService,
    get_asset_service,
)

AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

# Union type for all asset types
AssetType = ProgramAsset | ModelAsset | CompositionAsset


class AssetResponse(BaseModel):
    """Wrapper response for asset operations."""

    asset: AssetType = Field(discriminator="type")


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset: AssetType,
    current_user: CurrentUser,
    service: AssetServiceDep,
) -> AssetResponse:
    """Create a new asset (program, model, or composition).

    The asset type is determined by the 'type' field in the request body:
    - "program": Create a Python program with entrypoint and dependencies
    - "model": Create an LLM model configuration
    - "composition": Create a workflow linking programs and models

    The owner is automatically set to the authenticated user.
    """
    # Set owner to current user
    asset.owner = current_user.id

    try:
        created: AssetType
        if isinstance(asset, ProgramAsset):
            created = service.create_program(asset)
        elif isinstance(asset, ModelAsset):
            created = service.create_model(asset)
        elif isinstance(asset, CompositionAsset):
            created = service.create_composition(asset)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown asset type: {asset.type}",
            )
        return AssetResponse(asset=created)
    except AssetAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: str,
    current_user: CurrentUser,
    service: AssetServiceDep,
) -> AssetResponse:
    """Get an asset by ID.

    Searches across all asset types (programs, models, compositions) and
    returns the matching asset.
    """
    # Try each store in order
    program = service.get_program(asset_id)
    if program is not None:
        return AssetResponse(asset=program)

    model = service.get_model(asset_id)
    if model is not None:
        return AssetResponse(asset=model)

    composition = service.get_composition(asset_id)
    if composition is not None:
        return AssetResponse(asset=composition)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Asset not found: {asset_id}",
    )
