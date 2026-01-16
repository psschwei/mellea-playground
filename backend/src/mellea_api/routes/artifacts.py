"""Artifact routes for managing run outputs and files."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.artifact import Artifact, ArtifactType, ArtifactUsage
from mellea_api.services.artifact_collector import (
    ArtifactCollectorService,
    ArtifactTooLargeError,
    QuotaExceededError,
    get_artifact_collector_service,
)

ArtifactCollectorServiceDep = Annotated[
    ArtifactCollectorService, Depends(get_artifact_collector_service)
]

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class ArtifactResponse(BaseModel):
    """Response wrapper for artifact operations."""

    artifact: Artifact


class ArtifactsListResponse(BaseModel):
    """Response for list artifacts operation."""

    artifacts: list[Artifact]
    total: int


class ArtifactUsageResponse(BaseModel):
    """Response for usage query."""

    usage: ArtifactUsage
    quota_bytes: int = Field(alias="quotaBytes")
    usage_percent: float = Field(alias="usagePercent")

    class Config:
        populate_by_name = True


class UploadArtifactRequest(BaseModel):
    """Request body for uploading an artifact."""

    run_id: str = Field(alias="runId", description="ID of the run this artifact belongs to")
    name: str = Field(description="Name for the artifact")
    artifact_type: ArtifactType = Field(
        default=ArtifactType.FILE,
        alias="artifactType",
        description="Type of artifact",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional metadata")
    retention_days: int | None = Field(
        default=None,
        alias="retentionDays",
        description="Days to retain (None = default, 0 = never expire)",
    )

    class Config:
        populate_by_name = True


class BulkDeleteRequest(BaseModel):
    """Request body for bulk delete operation."""

    artifact_ids: list[str] = Field(
        alias="artifactIds", description="List of artifact IDs to delete"
    )

    class Config:
        populate_by_name = True


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete operation."""

    deleted_count: int = Field(alias="deletedCount")
    failed_count: int = Field(alias="failedCount")
    results: dict[str, bool | str]

    class Config:
        populate_by_name = True


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.get("", response_model=ArtifactsListResponse)
async def list_artifacts(
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
    run_id: str | None = Query(None, alias="runId", description="Filter by run ID"),
    artifact_type: ArtifactType | None = Query(
        None, alias="artifactType", description="Filter by artifact type"
    ),
    tags: list[str] | None = Query(None, description="Filter by tags (must have all)"),
    owner_only: bool = Query(
        True, alias="ownerOnly", description="Only show artifacts owned by current user"
    ),
) -> ArtifactsListResponse:
    """List artifacts with optional filters.

    Supports filtering by:
    - runId: Filter by run ID
    - artifactType: Filter by artifact type (file, directory, log, output)
    - tags: Filter by tags (artifact must have all specified tags)
    - ownerOnly: If true (default), only show artifacts owned by current user

    Returns artifacts visible to the authenticated user.
    """
    owner_id = current_user.id if owner_only else None

    artifacts = artifact_service.list_artifacts(
        owner_id=owner_id,
        run_id=run_id,
        artifact_type=artifact_type,
        tags=tags,
    )

    return ArtifactsListResponse(artifacts=artifacts, total=len(artifacts))


@router.get("/usage", response_model=ArtifactUsageResponse)
async def get_usage(
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> ArtifactUsageResponse:
    """Get the current user's artifact storage usage.

    Returns current usage, quota limit, and percentage used.
    """
    usage = artifact_service.get_user_usage(current_user.id)
    quota_bytes = current_user.quotas.max_storage_mb * 1024 * 1024
    usage_percent = (usage.total_bytes / quota_bytes * 100) if quota_bytes > 0 else 0.0

    return ArtifactUsageResponse(
        usage=usage,
        quotaBytes=quota_bytes,
        usagePercent=round(usage_percent, 2),
    )


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> ArtifactResponse:
    """Get artifact metadata by ID.

    Returns artifact details including name, size, type, and storage info.
    """
    artifact = artifact_service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        )

    # Check ownership (or admin access)
    if artifact.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this artifact",
        )

    return ArtifactResponse(artifact=artifact)


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> Response:
    """Download an artifact's content.

    Returns the raw file content with appropriate content-type and
    content-disposition headers for downloading.
    """
    artifact = artifact_service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        )

    # Check ownership (or admin access)
    if artifact.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this artifact",
        )

    try:
        content = artifact_service.get_artifact_content(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file not found on disk",
        ) from e

    return Response(
        content=content,
        media_type=artifact.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.name}"',
            "Content-Length": str(artifact.size_bytes),
        },
    )


@router.post("", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
    file: UploadFile,
    run_id: str = Query(alias="runId", description="ID of the run this artifact belongs to"),
    name: str | None = Query(None, description="Name for the artifact (defaults to filename)"),
    artifact_type: ArtifactType = Query(
        default=ArtifactType.FILE,
        alias="artifactType",
        description="Type of artifact",
    ),
    tags: list[str] | None = Query(None, description="Tags for categorization"),
    retention_days: int | None = Query(
        None,
        alias="retentionDays",
        description="Days to retain (None = default, 0 = never expire)",
    ),
) -> ArtifactResponse:
    """Upload a new artifact.

    Uploads a file as an artifact associated with a run. The file is stored
    and tracked with metadata including size, checksum, and expiration.

    Quota enforcement is applied - the upload will fail if it would exceed
    the user's storage quota.
    """
    # Read file content
    content = await file.read()
    artifact_name = name or file.filename or "unnamed"

    try:
        artifact = artifact_service.collect_artifact_from_bytes(
            run_id=run_id,
            owner_id=current_user.id,
            content=content,
            name=artifact_name,
            user_quotas=current_user.quotas,
            artifact_type=artifact_type,
            tags=tags or [],
            retention_days=retention_days,
        )
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        ) from e
    except ArtifactTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        ) from e

    return ArtifactResponse(artifact=artifact)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: str,
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> None:
    """Delete an artifact by ID.

    Permanently removes the artifact metadata and stored file.
    Only the artifact owner or an admin can delete an artifact.
    """
    artifact = artifact_service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        )

    # Check ownership (or admin access)
    if artifact.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this artifact",
        )

    artifact_service.delete_artifact(artifact_id)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_artifacts(
    request: BulkDeleteRequest,
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> BulkDeleteResponse:
    """Delete multiple artifacts at once.

    Only artifacts owned by the current user (or all if admin) can be deleted.
    The operation continues even if some deletions fail.

    Returns detailed results for each artifact ID.
    """
    results: dict[str, bool | str] = {}

    for artifact_id in request.artifact_ids:
        artifact = artifact_service.get_artifact(artifact_id)
        if artifact is None:
            results[artifact_id] = "Artifact not found"
            continue

        # Check ownership (or admin access)
        if artifact.owner_id != current_user.id and current_user.role.value != "admin":
            results[artifact_id] = "Permission denied"
            continue

        if artifact_service.delete_artifact(artifact_id):
            results[artifact_id] = True
        else:
            results[artifact_id] = "Failed to delete"

    deleted_count = sum(1 for v in results.values() if v is True)
    failed_count = len(results) - deleted_count

    return BulkDeleteResponse(
        deletedCount=deleted_count,
        failedCount=failed_count,
        results=results,
    )


@router.delete("/run/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifacts_for_run(
    run_id: str,
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> None:
    """Delete all artifacts associated with a run.

    Only the run owner or an admin can delete artifacts for a run.
    This is useful for cleaning up all artifacts when a run is deleted.
    """
    # Get artifacts to check ownership
    artifacts = artifact_service.list_artifacts(run_id=run_id)

    if not artifacts:
        return  # Nothing to delete

    # Check that all artifacts belong to the current user (or admin)
    if current_user.role.value != "admin":
        for artifact in artifacts:
            if artifact.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete artifacts for this run",
                )

    artifact_service.delete_artifacts_for_run(run_id)


@router.post("/recalculate-usage", response_model=ArtifactUsageResponse)
async def recalculate_usage(
    current_user: CurrentUser,
    artifact_service: ArtifactCollectorServiceDep,
) -> ArtifactUsageResponse:
    """Recalculate the current user's storage usage.

    Useful if usage tracking has become out of sync with actual artifacts.
    Scans all artifacts owned by the user and updates the usage record.
    """
    usage = artifact_service.recalculate_user_usage(current_user.id)
    quota_bytes = current_user.quotas.max_storage_mb * 1024 * 1024
    usage_percent = (usage.total_bytes / quota_bytes * 100) if quota_bytes > 0 else 0.0

    return ArtifactUsageResponse(
        usage=usage,
        quotaBytes=quota_bytes,
        usagePercent=round(usage_percent, 2),
    )
