"""Routes for GitHub import functionality."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.assets import DependencySpec, ProgramAsset, SlotMetadata
from mellea_api.services.github_import import (
    AnalysisError,
    GitHubImportError,
    GitHubImportService,
    InvalidRepositoryError,
    SessionNotFoundError,
    get_github_import_service,
)

logger = logging.getLogger(__name__)

GitHubImportServiceDep = Annotated[GitHubImportService, Depends(get_github_import_service)]

router = APIRouter(prefix="/api/v1/programs/import/github", tags=["import", "github"])


# Request/Response Models


class PythonProjectResponse(BaseModel):
    """Detected Python project within a repository."""

    path: str
    entrypoint: str | None = None
    confidence: float = 0.5
    indicators: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    """Analysis results for a repository."""

    root_files: list[str] = Field(default_factory=list, alias="rootFiles")
    python_projects: list[PythonProjectResponse] = Field(
        default_factory=list, alias="pythonProjects"
    )
    detected_dependencies: DependencySpec | None = Field(
        default=None, alias="detectedDependencies"
    )
    detected_slots: list[SlotMetadata] = Field(default_factory=list, alias="detectedSlots")
    repo_size: int = Field(default=0, alias="repoSize")
    file_count: int = Field(default=0, alias="fileCount")

    class Config:
        populate_by_name = True


class AnalyzeRequest(BaseModel):
    """Request to analyze a GitHub repository."""

    repo_url: str = Field(alias="repoUrl")
    branch: str = "main"
    access_token: str | None = Field(default=None, alias="accessToken")

    class Config:
        populate_by_name = True


class AnalyzeResponse(BaseModel):
    """Response from repository analysis."""

    status: str = "success"
    analysis: AnalysisResponse
    session_id: str = Field(alias="sessionId")
    repo_url: str = Field(alias="repoUrl")
    branch: str
    commit_sha: str = Field(alias="commitSha")

    class Config:
        populate_by_name = True


class ImportMetadata(BaseModel):
    """Metadata for the imported program."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    """Request to confirm and complete import."""

    session_id: str = Field(alias="sessionId")
    selected_path: str = Field(default=".", alias="selectedPath")
    metadata: ImportMetadata
    entrypoint: str | None = None
    dependencies: DependencySpec | None = None

    class Config:
        populate_by_name = True


class ImportSourceInfo(BaseModel):
    """Information about the import source."""

    type: str = "github"
    repo_url: str = Field(alias="repoUrl")
    branch: str
    commit: str
    imported_at: str = Field(alias="importedAt")

    class Config:
        populate_by_name = True


class ConfirmResponse(BaseModel):
    """Response from import confirmation."""

    asset: ProgramAsset
    import_source: ImportSourceInfo = Field(alias="importSource")

    class Config:
        populate_by_name = True


class CancelResponse(BaseModel):
    """Response from session cancellation."""

    cancelled: bool
    message: str


class ValidateUrlRequest(BaseModel):
    """Request to validate a GitHub URL."""

    url: str


class ValidateUrlResponse(BaseModel):
    """Response from URL validation."""

    valid: bool
    owner: str | None = None
    repo: str | None = None
    branch: str | None = None


# Endpoints


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_repository(
    request: AnalyzeRequest,
    current_user: CurrentUser,
    service: GitHubImportServiceDep,
) -> AnalyzeResponse:
    """Analyze a GitHub repository for import.

    Clones the repository to a temporary directory and analyzes its structure
    to detect Python projects, dependencies, and @generative slots.

    Args:
        request: Repository URL, branch, and optional access token

    Returns:
        Analysis results with session ID for subsequent confirmation

    Raises:
        400: If the repository URL is invalid
        422: If analysis fails
    """
    try:
        session = service.analyze_repository(
            repo_url=request.repo_url,
            branch=request.branch,
            access_token=request.access_token,
        )

        # Convert analysis to response model
        analysis = session.analysis
        analysis_response = AnalysisResponse(
            rootFiles=analysis.root_files,
            pythonProjects=[
                PythonProjectResponse(
                    path=p.path,
                    entrypoint=p.entrypoint,
                    confidence=p.confidence,
                    indicators=p.indicators,
                )
                for p in analysis.python_projects
            ],
            detectedDependencies=analysis.detected_dependencies,
            detectedSlots=analysis.detected_slots,
            repoSize=analysis.repo_size,
            fileCount=analysis.file_count,
        )

        return AnalyzeResponse(
            status="success",
            analysis=analysis_response,
            sessionId=session.session_id,
            repoUrl=session.repo_url,
            branch=session.branch,
            commitSha=session.commit_sha,
        )

    except InvalidRepositoryError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except AnalysisError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e


@router.post("/confirm", response_model=ConfirmResponse, status_code=status.HTTP_201_CREATED)
async def confirm_import(
    request: ConfirmRequest,
    current_user: CurrentUser,
    service: GitHubImportServiceDep,
) -> ConfirmResponse:
    """Confirm and complete the GitHub import.

    Uses a previously created analysis session to create a program from
    the cloned repository. Files are copied to the program's workspace.

    Args:
        request: Session ID, selected path, and program metadata

    Returns:
        Created program asset with import source information

    Raises:
        404: If the session is not found
        400: If import fails
    """
    try:
        # Get session to access import source info
        session = service.get_session(request.session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {request.session_id}")

        # Store session info before it's cleaned up
        repo_url = session.repo_url
        branch = session.branch
        commit_sha = session.commit_sha

        program = service.confirm_import(
            session_id=request.session_id,
            selected_path=request.selected_path,
            name=request.metadata.name,
            description=request.metadata.description,
            entrypoint=request.entrypoint,
            tags=request.metadata.tags,
            owner=current_user.id,
        )

        from datetime import datetime

        import_source = ImportSourceInfo(
            type="github",
            repoUrl=repo_url,
            branch=branch,
            commit=commit_sha,
            importedAt=datetime.utcnow().isoformat() + "Z",
        )

        return ConfirmResponse(
            asset=program,
            importSource=import_source,
        )

    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except GitHubImportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete("/session/{session_id}", response_model=CancelResponse)
async def cancel_session(
    session_id: str,
    current_user: CurrentUser,
    service: GitHubImportServiceDep,
) -> CancelResponse:
    """Cancel an import session and clean up temporary files.

    Use this if the user decides not to complete the import after analysis.

    Args:
        session_id: Session ID to cancel

    Returns:
        Cancellation status
    """
    cancelled = service.cancel_session(session_id)

    if cancelled:
        return CancelResponse(
            cancelled=True,
            message=f"Session {session_id} cancelled and cleaned up",
        )
    else:
        return CancelResponse(
            cancelled=False,
            message=f"Session {session_id} not found (may have already been cancelled or confirmed)",
        )


@router.post("/validate-url", response_model=ValidateUrlResponse)
async def validate_github_url(
    request: ValidateUrlRequest,
    current_user: CurrentUser,
    service: GitHubImportServiceDep,
) -> ValidateUrlResponse:
    """Validate a GitHub URL without cloning.

    Quick check to verify the URL format is valid for GitHub repositories.

    Args:
        request: URL to validate

    Returns:
        Validation result with parsed components if valid
    """
    parsed = service.parse_github_url(request.url)

    if parsed:
        owner, repo, branch = parsed
        return ValidateUrlResponse(
            valid=True,
            owner=owner,
            repo=repo,
            branch=branch,
        )
    else:
        return ValidateUrlResponse(valid=False)
