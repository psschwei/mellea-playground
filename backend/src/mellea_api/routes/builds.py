"""API routes for container image builds."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from mellea_api.models.build import BuildJob, BuildResult, LayerCacheEntry
from mellea_api.services import get_asset_service
from mellea_api.services.environment_builder import get_environment_builder_service
from mellea_api.services.kaniko_builder import get_kaniko_build_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/builds", tags=["builds"])


class BuildRequest(BaseModel):
    """Request to build an image for a program."""

    force_rebuild: bool = Field(
        default=False,
        description="Force rebuild even if cached",
        serialization_alias="forceRebuild",
    )
    push: bool = Field(
        default=False,
        description="Push the built image to the registry",
    )


class BuildStatusResponse(BaseModel):
    """Response containing build job status."""

    job: BuildJob


class CacheStatsResponse(BaseModel):
    """Response containing cache statistics."""

    total_entries: int = Field(serialization_alias="totalEntries")
    total_size_bytes: int | None = Field(serialization_alias="totalSizeBytes")
    entries: list[LayerCacheEntry]


# -----------------------------------------------------------------------------
# Build Operations
# -----------------------------------------------------------------------------


@router.post(
    "/programs/{program_id}",
    response_model=BuildResult,
    summary="Build image for program",
    description="Build a container image for the specified program. Uses layer caching for dependencies.",
)
async def build_program_image(
    program_id: Annotated[str, Path(description="Program ID")],
    request: BuildRequest | None = None,
) -> BuildResult:
    """Build a container image for a program.

    This endpoint triggers a Docker/Kaniko build for the specified program:
    1. Computes a cache key based on the program's dependencies
    2. Checks for a cached dependency layer
    3. Builds the dependency layer if not cached
    4. Builds the program layer on top of the dependency layer
    5. Optionally pushes to the configured registry

    Args:
        program_id: The ID of the program to build
        request: Build options (force rebuild, push to registry)

    Returns:
        BuildResult with success status, image tag, and timing information
    """
    asset_service = get_asset_service()
    builder = get_environment_builder_service()

    # Get the program
    program = asset_service.get_program(program_id)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program not found: {program_id}")

    # Get workspace path
    settings = builder.settings
    workspace_path = settings.data_dir / "workspaces" / program_id

    if not workspace_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Program workspace not found: {program_id}. Import the program first.",
        )

    # Build options
    force_rebuild = request.force_rebuild if request else False
    push = request.push if request else False

    logger.info(
        "Building image for program %s (force=%s, push=%s)",
        program_id,
        force_rebuild,
        push,
    )

    result = builder.build_image(
        program=program,
        workspace_path=workspace_path,
        force_rebuild=force_rebuild,
        push=push,
    )

    if result.success:
        # Update program with the new image tag
        program.image_tag = result.image_tag
        asset_service.update_program(program_id, program)
        logger.info("Build succeeded for %s: %s", program_id, result.image_tag)
    else:
        logger.error("Build failed for %s: %s", program_id, result.error_message)

    return result


@router.get(
    "/jobs/{job_name}",
    response_model=BuildStatusResponse,
    summary="Get build job status",
    description="Get the status of a Kaniko build job.",
)
async def get_build_job_status(
    job_name: Annotated[str, Path(description="Build job name")],
) -> BuildStatusResponse:
    """Get the status of a build job.

    For Kaniko builds, this returns the current status of the Kubernetes Job.

    Args:
        job_name: The name of the build job (returned from build_program_image)

    Returns:
        BuildStatusResponse with job status, timing, and any error messages
    """
    kaniko_service = get_kaniko_build_service()

    try:
        job = kaniko_service.get_build_status(job_name)
        return BuildStatusResponse(job=job)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/jobs/{job_name}/logs",
    response_model=dict,
    summary="Get build job logs",
    description="Get logs from a build job.",
)
async def get_build_job_logs(
    job_name: Annotated[str, Path(description="Build job name")],
    tail_lines: Annotated[int, Query(description="Number of log lines", ge=1, le=1000)] = 100,
) -> dict:
    """Get logs from a build job.

    Args:
        job_name: The name of the build job
        tail_lines: Number of log lines to return (default: 100)

    Returns:
        Dictionary with logs field containing the log output
    """
    kaniko_service = get_kaniko_build_service()

    try:
        logs = kaniko_service.get_build_logs(job_name, tail_lines=tail_lines)
        return {"logs": logs}
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/jobs/{job_name}",
    summary="Delete build job",
    description="Delete a completed or failed build job.",
)
async def delete_build_job(
    job_name: Annotated[str, Path(description="Build job name")],
) -> dict:
    """Delete a build job and its resources.

    Args:
        job_name: The name of the build job to delete

    Returns:
        Dictionary with deleted status
    """
    kaniko_service = get_kaniko_build_service()
    deleted = kaniko_service.delete_build_job(job_name)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Build job not found: {job_name}")

    return {"deleted": True, "job_name": job_name}


# -----------------------------------------------------------------------------
# Cache Operations
# -----------------------------------------------------------------------------


@router.get(
    "/cache",
    response_model=CacheStatsResponse,
    summary="Get layer cache stats",
    description="Get statistics about the dependency layer cache.",
)
async def get_cache_stats() -> CacheStatsResponse:
    """Get layer cache statistics.

    Returns:
        CacheStatsResponse with total entries, size, and list of cache entries
    """
    builder = get_environment_builder_service()
    entries = builder.list_cache_entries()

    total_size = sum(e.size_bytes for e in entries if e.size_bytes)

    return CacheStatsResponse(
        total_entries=len(entries),
        total_size_bytes=total_size if total_size > 0 else None,
        entries=entries,
    )


@router.delete(
    "/cache/{cache_key}",
    summary="Invalidate cache entry",
    description="Remove a specific cache entry.",
)
async def invalidate_cache_entry(
    cache_key: Annotated[str, Path(description="Cache key to invalidate")],
) -> dict:
    """Invalidate a specific cache entry.

    This removes the cache entry but does not delete the Docker image.

    Args:
        cache_key: The cache key to invalidate

    Returns:
        Dictionary with invalidated status
    """
    builder = get_environment_builder_service()
    invalidated = builder.invalidate_cache_entry(cache_key)

    if not invalidated:
        raise HTTPException(status_code=404, detail=f"Cache entry not found: {cache_key}")

    return {"invalidated": True, "cache_key": cache_key}


@router.post(
    "/cache/prune",
    summary="Prune stale cache entries",
    description="Remove cache entries older than the specified age.",
)
async def prune_cache(
    max_age_days: Annotated[int, Query(description="Max age in days", ge=1)] = 30,
) -> dict:
    """Prune stale cache entries.

    Removes cache entries that haven't been used in the specified number of days.
    Also attempts to remove the associated Docker images.

    Args:
        max_age_days: Maximum age in days before pruning

    Returns:
        Dictionary with count of pruned entries
    """
    builder = get_environment_builder_service()
    pruned = builder.prune_stale_cache_entries(max_age_days=max_age_days)

    return {"pruned": pruned, "max_age_days": max_age_days}
