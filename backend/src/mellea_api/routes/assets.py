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
from mellea_api.models.build import BuildJob, BuildJobStatus, BuildResult
from mellea_api.models.common import DependencySource, ImageBuildStatus
from mellea_api.services.assets import (
    AssetAlreadyExistsError,
    AssetService,
    get_asset_service,
)
from mellea_api.services.environment_builder import get_environment_builder_service
from mellea_api.services.kaniko_builder import get_kaniko_build_service

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


class BuildStatusResponse(BaseModel):
    """Response for build status polling."""

    build: BuildJob
    logs: str | None = None


class UpdateAssetRequest(BaseModel):
    """Request model for updating asset metadata.

    All fields are optional - only provided fields will be updated.
    """

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    version: str | None = None


class DeleteAssetResponse(BaseModel):
    """Response for delete asset operation."""

    deleted: bool
    message: str


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

    # Handle async Kaniko builds differently
    if result.build_job_name:
        # Kaniko build started - job runs asynchronously
        # Keep status as BUILDING, update image_tag with expected value
        program.image_tag = result.image_tag
        # Status stays BUILDING until job completes
        service.update_program(asset_id, program)
        return BuildImageResponse(result=result)

    # Synchronous Docker build - update program with final result
    if result.success:
        program.image_tag = result.image_tag
        program.image_build_status = ImageBuildStatus.READY
        program.image_build_error = None
    else:
        program.image_build_status = ImageBuildStatus.FAILED
        program.image_build_error = result.error_message

    service.update_program(asset_id, program)

    return BuildImageResponse(result=result)


@router.get("/{asset_id}/build/status", response_model=BuildStatusResponse)
async def get_build_status(
    asset_id: str,
    current_user: CurrentUser,
    service: AssetServiceDep,
    include_logs: bool = Query(default=False, alias="includeLogs"),
) -> BuildStatusResponse:
    """Get the status of an in-progress Kaniko build.

    This endpoint is used to poll for build completion when using the
    Kaniko build backend. For Docker builds, the build completes
    synchronously and this endpoint is not needed.

    Args:
        asset_id: ID of the program asset being built
        include_logs: Whether to include build logs in response

    Returns:
        Build status and optionally logs

    Raises:
        404: If the asset or build job is not found
    """
    # Get the program
    program = service.get_program(asset_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset not found: {asset_id}",
        )

    # Generate the expected job name
    job_name = f"mellea-build-{asset_id[:8].lower()}"

    try:
        kaniko_service = get_kaniko_build_service()
        build = kaniko_service.get_build_status(job_name)

        # Update program status if build completed
        if build.status == BuildJobStatus.SUCCEEDED:
            program.image_build_status = ImageBuildStatus.READY
            program.image_build_error = None
            service.update_program(asset_id, program)
        elif build.status == BuildJobStatus.FAILED:
            program.image_build_status = ImageBuildStatus.FAILED
            program.image_build_error = build.error_message
            service.update_program(asset_id, program)

        # Get logs if requested
        logs = None
        if include_logs:
            logs = kaniko_service.get_build_logs(job_name)

        return BuildStatusResponse(build=build, logs=logs)

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: str,
    update: UpdateAssetRequest,
    current_user: CurrentUser,
    service: AssetServiceDep,
) -> AssetResponse:
    """Update an asset's metadata.

    Only the owner of an asset can update it. Supports partial updates -
    only fields provided in the request body will be modified.

    Updateable fields:
    - name: Asset display name
    - description: Asset description
    - tags: List of tags
    - version: Version string
    """
    # Try to find the asset across all stores
    program = service.get_program(asset_id)
    if program is not None:
        # Check ownership
        if program.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this asset",
            )
        # Apply updates
        if update.name is not None:
            program.name = update.name
        if update.description is not None:
            program.description = update.description
        if update.tags is not None:
            program.tags = update.tags
        if update.version is not None:
            program.version = update.version
        updated = service.update_program(asset_id, program)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update asset",
            )
        return AssetResponse(asset=updated)

    model = service.get_model(asset_id)
    if model is not None:
        if model.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this asset",
            )
        if update.name is not None:
            model.name = update.name
        if update.description is not None:
            model.description = update.description
        if update.tags is not None:
            model.tags = update.tags
        if update.version is not None:
            model.version = update.version
        updated_model = service.update_model(asset_id, model)
        if updated_model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update asset",
            )
        return AssetResponse(asset=updated_model)

    composition = service.get_composition(asset_id)
    if composition is not None:
        if composition.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this asset",
            )
        if update.name is not None:
            composition.name = update.name
        if update.description is not None:
            composition.description = update.description
        if update.tags is not None:
            composition.tags = update.tags
        if update.version is not None:
            composition.version = update.version
        updated_composition = service.update_composition(asset_id, composition)
        if updated_composition is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update asset",
            )
        return AssetResponse(asset=updated_composition)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Asset not found: {asset_id}",
    )


@router.delete("/{asset_id}", response_model=DeleteAssetResponse)
async def delete_asset(
    asset_id: str,
    current_user: CurrentUser,
    service: AssetServiceDep,
) -> DeleteAssetResponse:
    """Delete an asset (soft delete with ownership check).

    Only the owner of an asset can delete it. For programs, this also
    removes the associated workspace directory.
    """
    # Try to find the asset across all stores
    program = service.get_program(asset_id)
    if program is not None:
        if program.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this asset",
            )
        deleted = service.delete_program(asset_id)
        return DeleteAssetResponse(
            deleted=deleted,
            message=f"Program '{program.name}' deleted successfully",
        )

    model = service.get_model(asset_id)
    if model is not None:
        if model.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this asset",
            )
        deleted = service.delete_model(asset_id)
        return DeleteAssetResponse(
            deleted=deleted,
            message=f"Model '{model.name}' deleted successfully",
        )

    composition = service.get_composition(asset_id)
    if composition is not None:
        if composition.owner != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this asset",
            )
        deleted = service.delete_composition(asset_id)
        return DeleteAssetResponse(
            deleted=deleted,
            message=f"Composition '{composition.name}' deleted successfully",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Asset not found: {asset_id}",
    )
