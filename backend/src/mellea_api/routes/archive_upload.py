"""Routes for archive upload functionality."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.assets import DependencySpec, ProgramAsset, SlotMetadata
from mellea_api.services.archive_upload import (
    AnalysisError,
    ArchiveUploadError,
    ArchiveUploadService,
    FileTooLargeError,
    InvalidArchiveError,
    SessionNotFoundError,
    get_archive_upload_service,
)

logger = logging.getLogger(__name__)

ArchiveUploadServiceDep = Annotated[ArchiveUploadService, Depends(get_archive_upload_service)]

router = APIRouter(prefix="/api/v1/programs/import/upload", tags=["import", "upload"])


# Request/Response Models


class ExtractedFileResponse(BaseModel):
    """File extracted from archive."""

    path: str
    size: int
    is_python: bool = Field(alias="isPython")

    class Config:
        populate_by_name = True


class UploadAnalysisResponse(BaseModel):
    """Analysis results for uploaded archive."""

    root_files: list[str] = Field(default_factory=list, alias="rootFiles")
    all_files: list[ExtractedFileResponse] = Field(default_factory=list, alias="allFiles")
    detected_entrypoint: str | None = Field(default=None, alias="detectedEntrypoint")
    detected_dependencies: DependencySpec | None = Field(
        default=None, alias="detectedDependencies"
    )
    detected_slots: list[SlotMetadata] = Field(default_factory=list, alias="detectedSlots")
    total_size: int = Field(default=0, alias="totalSize")
    file_count: int = Field(default=0, alias="fileCount")

    class Config:
        populate_by_name = True


class UploadResponse(BaseModel):
    """Response from file upload and analysis."""

    status: str = "success"
    analysis: UploadAnalysisResponse
    session_id: str = Field(alias="sessionId")
    filename: str

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
    metadata: ImportMetadata
    entrypoint: str | None = None
    dependencies: DependencySpec | None = None

    class Config:
        populate_by_name = True


class ImportSourceInfo(BaseModel):
    """Information about the import source."""

    type: str = "upload"
    filename: str
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


# Endpoints


@router.post("/analyze", response_model=UploadResponse)
async def upload_and_analyze(
    file: UploadFile,
    current_user: CurrentUser,
    service: ArchiveUploadServiceDep,
) -> UploadResponse:
    """Upload and analyze an archive file.

    Accepts zip, tar.gz, or tar files. Extracts contents to a temporary
    directory and analyzes for Python projects, dependencies, and @generative slots.

    Args:
        file: Uploaded archive file (zip, tar.gz, tar)

    Returns:
        Analysis results with session ID for subsequent confirmation

    Raises:
        400: If file is invalid or too large
        422: If analysis fails
    """
    try:
        # Read file content
        content = await file.read()
        filename = file.filename or "upload.zip"

        session = service.process_upload(content, filename)

        # Convert analysis to response model
        analysis = session.analysis
        analysis_response = UploadAnalysisResponse(
            rootFiles=analysis.root_files,
            allFiles=[
                ExtractedFileResponse(
                    path=f.path,
                    size=f.size,
                    isPython=f.is_python,
                )
                for f in analysis.all_files
            ],
            detectedEntrypoint=analysis.detected_entrypoint,
            detectedDependencies=analysis.detected_dependencies,
            detectedSlots=analysis.detected_slots,
            totalSize=analysis.total_size,
            fileCount=analysis.file_count,
        )

        return UploadResponse(
            status="success",
            analysis=analysis_response,
            sessionId=session.session_id,
            filename=filename,
        )

    except FileTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except InvalidArchiveError as e:
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
    service: ArchiveUploadServiceDep,
) -> ConfirmResponse:
    """Confirm and complete the upload import.

    Uses a previously created upload session to create a program from
    the extracted archive. Files are copied to the program's workspace.

    Args:
        request: Session ID and program metadata

    Returns:
        Created program asset with import source information

    Raises:
        404: If the session is not found
        400: If import fails
    """
    try:
        # Get session to access filename
        session = service.get_session(request.session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {request.session_id}")

        filename = session.filename

        program = service.confirm_import(
            session_id=request.session_id,
            name=request.metadata.name,
            description=request.metadata.description,
            entrypoint=request.entrypoint,
            tags=request.metadata.tags,
            owner=current_user.id,
        )

        import_source = ImportSourceInfo(
            type="upload",
            filename=filename,
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
    except ArchiveUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete("/session/{session_id}", response_model=CancelResponse)
async def cancel_session(
    session_id: str,
    current_user: CurrentUser,
    service: ArchiveUploadServiceDep,
) -> CancelResponse:
    """Cancel an upload session and clean up temporary files.

    Use this if the user decides not to complete the import after upload.

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
