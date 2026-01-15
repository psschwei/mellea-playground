"""Archive upload service for handling file uploads and archive extraction."""

import logging
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.assets import (
    DependencySpec,
    ProgramAsset,
    SlotMetadata,
)
from mellea_api.models.common import DependencySource
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.program_validator import (
    ProgramValidator,
    get_program_validator,
)

logger = logging.getLogger(__name__)


class ArchiveUploadError(Exception):
    """Base exception for archive upload errors."""

    pass


class InvalidArchiveError(ArchiveUploadError):
    """Raised when the uploaded archive is invalid or cannot be extracted."""

    pass


class AnalysisError(ArchiveUploadError):
    """Raised when archive analysis fails."""

    pass


class SessionNotFoundError(ArchiveUploadError):
    """Raised when an upload session is not found."""

    pass


class FileTooLargeError(ArchiveUploadError):
    """Raised when the uploaded file exceeds size limits."""

    pass


@dataclass
class ExtractedFile:
    """A file extracted from an archive."""

    path: str  # Relative path within archive
    size: int
    is_python: bool = False


@dataclass
class UploadAnalysisResult:
    """Results of archive analysis."""

    root_files: list[str] = field(default_factory=list)
    all_files: list[ExtractedFile] = field(default_factory=list)
    detected_entrypoint: str | None = None
    detected_dependencies: DependencySpec | None = None
    detected_slots: list[SlotMetadata] = field(default_factory=list)
    total_size: int = 0
    file_count: int = 0


@dataclass
class UploadSession:
    """Temporary session storing upload analysis for confirmation."""

    session_id: str
    filename: str
    temp_dir: Path
    analysis: UploadAnalysisResult


class ArchiveUploadService:
    """Service for handling archive uploads and analysis.

    Handles zip and tar.gz file uploads, extraction, and analysis for
    Python projects. Similar flow to GitHub import.

    Example:
        ```python
        service = get_archive_upload_service()

        # Process uploaded file
        session = await service.process_upload(file_content, "program.zip")

        # Confirm import
        program = await service.confirm_import(
            session_id=session.session_id,
            name="my-program",
            description="My uploaded program"
        )
        ```
    """

    # Supported archive extensions
    SUPPORTED_EXTENSIONS = [".zip", ".tar.gz", ".tgz", ".tar"]

    # Maximum file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    # Maximum number of files to extract
    MAX_FILES = 500

    def __init__(
        self,
        settings: Settings | None = None,
        asset_service: AssetService | None = None,
        validator: ProgramValidator | None = None,
    ) -> None:
        """Initialize the archive upload service."""
        self.settings = settings or get_settings()
        self.asset_service = asset_service or get_asset_service()
        self.validator = validator or get_program_validator()
        self._sessions: dict[str, UploadSession] = {}

    def process_upload(
        self,
        file_content: bytes,
        filename: str,
    ) -> UploadSession:
        """Process an uploaded archive file.

        Args:
            file_content: Raw file bytes
            filename: Original filename

        Returns:
            UploadSession with analysis results

        Raises:
            FileTooLargeError: If file exceeds size limit
            InvalidArchiveError: If file is not a valid archive
            AnalysisError: If analysis fails
        """
        # Check file size
        if len(file_content) > self.MAX_FILE_SIZE:
            raise FileTooLargeError(
                f"File size ({len(file_content)} bytes) exceeds maximum "
                f"({self.MAX_FILE_SIZE} bytes)"
            )

        # Validate extension
        ext = self._get_extension(filename)
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise InvalidArchiveError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="mellea-upload-"))
        logger.info(f"Extracting archive to {temp_dir}")

        try:
            # Write file to temp location
            archive_path = temp_dir / filename
            archive_path.write_bytes(file_content)

            # Extract archive
            extract_dir = temp_dir / "extracted"
            extract_dir.mkdir()
            self._extract_archive(archive_path, extract_dir, ext)

            # Handle nested directory (common in zips)
            extract_dir = self._unwrap_single_directory(extract_dir)

            # Analyze extracted contents
            analysis = self._analyze_directory(extract_dir)

            # Create session
            session_id = str(uuid4())
            session = UploadSession(
                session_id=session_id,
                filename=filename,
                temp_dir=extract_dir,
                analysis=analysis,
            )
            self._sessions[session_id] = session

            logger.info(f"Created upload session {session_id}")
            return session

        except (zipfile.BadZipFile, tarfile.TarError) as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise InvalidArchiveError(f"Invalid archive file: {e}") from e
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            if isinstance(e, ArchiveUploadError):
                raise
            raise AnalysisError(f"Analysis failed: {e}") from e

    def _get_extension(self, filename: str) -> str:
        """Get the file extension, handling compound extensions."""
        lower = filename.lower()
        if lower.endswith(".tar.gz"):
            return ".tar.gz"
        if lower.endswith(".tgz"):
            return ".tgz"
        if lower.endswith(".tar"):
            return ".tar"
        if lower.endswith(".zip"):
            return ".zip"
        return Path(filename).suffix.lower()

    def _extract_archive(self, archive_path: Path, dest: Path, ext: str) -> None:
        """Extract an archive to a destination directory."""
        file_count = 0

        if ext == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if file_count >= self.MAX_FILES:
                        raise InvalidArchiveError(
                            f"Archive contains too many files (max {self.MAX_FILES})"
                        )
                    # Skip directories and hidden files
                    if info.is_dir() or info.filename.startswith("__MACOSX"):
                        continue
                    # Security: prevent path traversal
                    if info.filename.startswith("/") or ".." in info.filename:
                        continue
                    zf.extract(info, dest)
                    file_count += 1

        elif ext in [".tar.gz", ".tgz", ".tar"]:
            # Open tar file with appropriate mode
            # Using try/finally instead of with statement for mypy Literal type compatibility
            if ext in [".tar.gz", ".tgz"]:
                tf = tarfile.open(str(archive_path), "r:gz")  # noqa: SIM115
            else:
                tf = tarfile.open(str(archive_path), "r")  # noqa: SIM115

            try:
                for member in tf.getmembers():
                    if file_count >= self.MAX_FILES:
                        raise InvalidArchiveError(
                            f"Archive contains too many files (max {self.MAX_FILES})"
                        )
                    # Skip directories and hidden files
                    if member.isdir():
                        continue
                    # Security: prevent path traversal
                    if member.name.startswith("/") or ".." in member.name:
                        continue
                    tf.extract(member, dest, filter="data")
                    file_count += 1
            finally:
                tf.close()

        logger.info(f"Extracted {file_count} files")

    def _unwrap_single_directory(self, extract_dir: Path) -> Path:
        """If archive contains a single root directory, unwrap it."""
        items = list(extract_dir.iterdir())
        if len(items) == 1 and items[0].is_dir():
            return items[0]
        return extract_dir

    def _analyze_directory(self, root: Path) -> UploadAnalysisResult:
        """Analyze extracted directory for Python project structure."""
        # List root files
        root_files = [
            f.name + ("/" if f.is_dir() else "")
            for f in sorted(root.iterdir())
            if not f.name.startswith(".")
        ]

        # Collect all files
        all_files: list[ExtractedFile] = []
        total_size = 0

        for file_path in root.rglob("*"):
            if file_path.is_file():
                # Skip hidden files
                if any(part.startswith(".") for part in file_path.parts):
                    continue
                rel_path = str(file_path.relative_to(root))
                size = file_path.stat().st_size
                is_python = file_path.suffix == ".py"
                all_files.append(ExtractedFile(path=rel_path, size=size, is_python=is_python))
                total_size += size

        # Use validator to detect entrypoint
        entrypoint = self.validator.detect_entrypoint(root)

        # Use validator to extract dependencies
        dependencies = self.validator.extract_dependencies(root)

        # Use validator to detect slots
        slots = self.validator.detect_slots(root)

        return UploadAnalysisResult(
            root_files=root_files,
            all_files=all_files,
            detected_entrypoint=entrypoint,
            detected_dependencies=dependencies,
            detected_slots=slots,
            total_size=total_size,
            file_count=len(all_files),
        )

    def get_session(self, session_id: str) -> UploadSession | None:
        """Get an upload session by ID."""
        return self._sessions.get(session_id)

    def confirm_import(
        self,
        session_id: str,
        name: str,
        description: str,
        entrypoint: str | None = None,
        tags: list[str] | None = None,
        owner: str = "",
    ) -> ProgramAsset:
        """Confirm and complete the import from a session.

        Args:
            session_id: Upload session ID
            name: Program name
            description: Program description
            entrypoint: Override entrypoint (uses detected if not provided)
            tags: Program tags
            owner: Owner user ID

        Returns:
            Created ProgramAsset

        Raises:
            SessionNotFoundError: If session not found
            ArchiveUploadError: If import fails
        """
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        try:
            # Determine entrypoint
            final_entrypoint = entrypoint or session.analysis.detected_entrypoint or "main.py"

            # Determine dependencies
            deps = session.analysis.detected_dependencies or DependencySpec(
                source=DependencySource.MANUAL
            )

            # Create the program
            program = ProgramAsset(
                name=name,
                description=description,
                tags=tags or ["imported", "upload"],
                owner=owner,
                entrypoint=final_entrypoint,
                projectRoot="",
                dependencies=deps,
                exportedSlots=session.analysis.detected_slots,
            )

            created = self.asset_service.create_program(program)
            created.project_root = f"workspaces/{created.id}"

            # Copy files from temp directory to workspace
            self._copy_files_to_workspace(session.temp_dir, created.id)

            # Update program with project root
            self.asset_service.update_program(created.id, created)

            logger.info(f"Imported program {created.id} from upload {session.filename}")

            # Clean up session
            self._cleanup_session(session_id)

            return created

        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise ArchiveUploadError(f"Import failed: {e}") from e

    def _copy_files_to_workspace(self, source_dir: Path, program_id: str) -> None:
        """Copy files from source directory to program workspace."""
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                # Skip hidden files
                if any(part.startswith(".") for part in file_path.parts):
                    continue

                relative_path = file_path.relative_to(source_dir)
                try:
                    content = file_path.read_text(encoding="utf-8")
                    self.asset_service.write_workspace_file(
                        program_id, str(relative_path), content
                    )
                except UnicodeDecodeError:
                    logger.warning(f"Skipping binary file: {relative_path}")

    def _cleanup_session(self, session_id: str) -> None:
        """Clean up an upload session."""
        session = self._sessions.pop(session_id, None)
        if session:
            # Go up to the temp root (parent of extracted dir)
            temp_root = session.temp_dir.parent
            if "mellea-upload-" in str(temp_root):
                shutil.rmtree(temp_root, ignore_errors=True)
            logger.info(f"Cleaned up session {session_id}")

    def cancel_session(self, session_id: str) -> bool:
        """Cancel and clean up an upload session."""
        if session_id in self._sessions:
            self._cleanup_session(session_id)
            return True
        return False


# Global service instance
_archive_upload_service: ArchiveUploadService | None = None


def get_archive_upload_service() -> ArchiveUploadService:
    """Get the global archive upload service instance."""
    global _archive_upload_service
    if _archive_upload_service is None:
        _archive_upload_service = ArchiveUploadService()
    return _archive_upload_service
