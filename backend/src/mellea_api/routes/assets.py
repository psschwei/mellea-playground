"""Asset routes for creating and retrieving catalog assets."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.assets import (
    CompositionAsset,
    DependencySpec,
    ModelAsset,
    ProgramAsset,
)
from mellea_api.models.build import BuildResult
from mellea_api.models.common import DependencySource, ImageBuildStatus
from mellea_api.services.assets import (
    AssetAlreadyExistsError,
    AssetService,
    get_asset_service,
)
from mellea_api.services.environment_builder import get_environment_builder_service

AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

# Union type for all asset types
AssetType = ProgramAsset | ModelAsset | CompositionAsset


class CreateProgramRequest(BaseModel):
    """Request model for creating a program from source code."""

    type: Literal["program"] = "program"
    name: str
    description: str = ""
    entrypoint: str = "main.py"
    source_code: str = Field(alias="sourceCode")
    tags: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


# Union type for create asset requests
# CreateProgramRequest must come before ProgramAsset so it's checked first
# (ProgramAsset would fail validation on sourceCode requests)
CreateAssetRequest = CreateProgramRequest | ProgramAsset | ModelAsset | CompositionAsset


class AssetResponse(BaseModel):
    """Wrapper response for asset operations."""

    asset: AssetType = Field(discriminator="type")


class AssetsListResponse(BaseModel):
    """Response for list assets operation."""

    assets: list[AssetType]
    total: int


class BuildImageRequest(BaseModel):
    """Request model for building a program image."""

    force_rebuild: bool = Field(default=False, alias="forceRebuild")
    push: bool = Field(default=False)

    class Config:
        populate_by_name = True


class BuildImageResponse(BaseModel):
    """Response for build image operation."""

    result: BuildResult


@router.get("", response_model=AssetsListResponse)
async def list_assets(
    current_user: CurrentUser,
    service: AssetServiceDep,
    type: str | None = Query(None, description="Filter by asset type (program, model, composition)"),
    owner: str | None = Query(None, description="Filter by owner ID"),
    tags: list[str] | None = Query(None, description="Filter by tags (must have all specified)"),
    q: str | None = Query(None, description="Search in name and description"),
) -> AssetsListResponse:
    """List assets with optional filters.

    Supports filtering by:
    - type: Filter by asset type ("program", "model", "composition")
    - owner: Filter by owner ID
    - tags: Filter by tags (assets must have all specified tags)
    - q: Text search in name and description

    Returns assets visible to the authenticated user.
    """
    # Use the search method which supports all filters
    results = service.search(
        query=q,
        asset_type=type,
        owner=owner,
        tags=tags,
    )

    # Convert to full asset types
    assets: list[AssetType] = []
    for result in results:
        if isinstance(result, (ProgramAsset, ModelAsset, CompositionAsset)):
            assets.append(result)
        else:
            # If it's just AssetMetadata, look up the full asset
            program = service.get_program(result.id)
            if program is not None:
                assets.append(program)
                continue
            model = service.get_model(result.id)
            if model is not None:
                assets.append(model)
                continue
            composition = service.get_composition(result.id)
            if composition is not None:
                assets.append(composition)

    return AssetsListResponse(assets=assets, total=len(assets))


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset: CreateAssetRequest,
    current_user: CurrentUser,
    service: AssetServiceDep,
) -> AssetResponse:
    """Create a new asset (program, model, or composition).

    The asset type is determined by the 'type' field in the request body:
    - "program": Create a Python program with entrypoint and source code
    - "model": Create an LLM model configuration
    - "composition": Create a workflow linking programs and models

    The owner is automatically set to the authenticated user.
    """
    try:
        created: AssetType
        if isinstance(asset, CreateProgramRequest):
            # Convert CreateProgramRequest to ProgramAsset
            program = ProgramAsset(
                name=asset.name,
                description=asset.description,
                tags=asset.tags,
                owner=current_user.id,
                entrypoint=asset.entrypoint,
                projectRoot="",  # Will be set after workspace creation
                dependencies=DependencySpec(source=DependencySource.MANUAL),
            )
            created = service.create_program(program)
            # Update project_root to point to workspace
            created.project_root = f"workspaces/{created.id}"
            service.update_program(created.id, created)
            # Write source code to workspace
            service.write_workspace_file(created.id, asset.entrypoint, asset.source_code)
        elif isinstance(asset, ProgramAsset):
            # Full ProgramAsset with projectRoot/dependencies provided directly
            asset.owner = current_user.id
            created = service.create_program(asset)
        elif isinstance(asset, ModelAsset):
            asset.owner = current_user.id
            created = service.create_model(asset)
        elif isinstance(asset, CompositionAsset):
            asset.owner = current_user.id
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


@router.post("/{asset_id}/build", response_model=BuildImageResponse)
async def build_asset_image(
    asset_id: str,
    current_user: CurrentUser,
    service: AssetServiceDep,
    request: BuildImageRequest | None = None,
) -> BuildImageResponse:
    """Build a container image for a program asset.

    Triggers the build process for the program's container image. The built image
    tag will be stored on the program asset for subsequent runs.

    Args:
        asset_id: ID of the program asset to build
        request: Optional build parameters (forceRebuild, push)

    Returns:
        Build result with success status, image tag, and timing information.

    Raises:
        404: If the asset is not found
        400: If the asset is not a program (only programs can be built)
    """
    # Get the program
    program = service.get_program(asset_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset not found: {asset_id}",
        )

    # Get workspace path
    workspace_path = service.settings.data_dir / "workspaces" / asset_id

    # Update status to building
    program.image_build_status = ImageBuildStatus.BUILDING
    program.image_build_error = None
    service.update_program(asset_id, program)

    # Get build parameters
    force_rebuild = request.force_rebuild if request else False
    push = request.push if request else False

    # Build the image
    builder = get_environment_builder_service()
    result = builder.build_image(
        program=program,
        workspace_path=workspace_path,
        force_rebuild=force_rebuild,
        push=push,
    )

    # Update program with result
    if result.success:
        program.image_tag = result.image_tag
        program.image_build_status = ImageBuildStatus.READY
        program.image_build_error = None
    else:
        program.image_build_status = ImageBuildStatus.FAILED
        program.image_build_error = result.error_message

    service.update_program(asset_id, program)

    return BuildImageResponse(result=result)
