"""GitHub import service for cloning and analyzing repositories."""

import ast
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

# GitPython is optional - allows tests to run without it installed
try:
    from git import Repo
    from git.exc import GitCommandError

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    Repo = None  # type: ignore[misc, assignment]
    GitCommandError = Exception  # type: ignore[misc, assignment]

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.assets import (
    DependencySpec,
    PackageRef,
    ProgramAsset,
    SlotMetadata,
    SlotSignature,
)
from mellea_api.models.common import DependencySource
from mellea_api.services.assets import AssetService, get_asset_service

logger = logging.getLogger(__name__)


class GitHubImportError(Exception):
    """Raised when GitHub import operations fail."""

    pass


class InvalidRepositoryError(GitHubImportError):
    """Raised when the repository URL is invalid or inaccessible."""

    pass


class AnalysisError(GitHubImportError):
    """Raised when repository analysis fails."""

    pass


class SessionNotFoundError(GitHubImportError):
    """Raised when an import session is not found."""

    pass


@dataclass
class PythonProject:
    """Detected Python project within a repository."""

    path: str  # Relative path within repo (e.g., "." or "examples/basic")
    entrypoint: str | None = None
    confidence: float = 0.5
    indicators: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Results of repository analysis."""

    root_files: list[str] = field(default_factory=list)
    python_projects: list[PythonProject] = field(default_factory=list)
    detected_dependencies: DependencySpec | None = None
    detected_slots: list[SlotMetadata] = field(default_factory=list)
    repo_size: int = 0
    file_count: int = 0


@dataclass
class ImportSession:
    """Temporary session storing analysis results for confirmation."""

    session_id: str
    repo_url: str
    branch: str
    commit_sha: str
    temp_dir: Path
    analysis: AnalysisResult


class GitHubImportService:
    """Service for importing programs from GitHub repositories.

    Handles repository cloning, analysis, and program creation from GitHub.
    Uses temporary directories for cloning and caches analysis in import sessions.

    Example:
        ```python
        service = get_github_import_service()

        # Analyze repository
        session = await service.analyze_repository(
            repo_url="https://github.com/owner/repo",
            branch="main"
        )

        # Confirm import
        program = await service.confirm_import(
            session_id=session.session_id,
            selected_path=".",
            name="My Program",
            description="Imported from GitHub"
        )
        ```
    """

    # Pattern for parsing GitHub URLs
    GITHUB_URL_PATTERNS = [
        re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$"),
        re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$"),
        re.compile(r"^https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(.*)$"),
    ]

    # Files that indicate a Python project
    PROJECT_INDICATORS = [
        "pyproject.toml",
        "setup.py",
        "requirements.txt",
        "main.py",
        "__main__.py",
    ]

    # Candidate entrypoint files (in priority order)
    ENTRYPOINT_CANDIDATES = [
        "main.py",
        "app.py",
        "run.py",
        "__main__.py",
        "src/main.py",
        "src/__main__.py",
        "src/app.py",
    ]

    # Mellea decorators to detect
    MELLEA_DECORATORS = ["generative", "verifier", "requirement"]

    def __init__(
        self,
        settings: Settings | None = None,
        asset_service: AssetService | None = None,
    ) -> None:
        """Initialize the GitHub import service.

        Args:
            settings: Application settings (uses default if not provided)
            asset_service: Asset service for creating programs (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self.asset_service = asset_service or get_asset_service()
        self._sessions: dict[str, ImportSession] = {}

    def parse_github_url(self, url: str) -> tuple[str, str, str | None] | None:
        """Parse a GitHub URL into owner, repo, and optional branch.

        Args:
            url: GitHub repository URL

        Returns:
            Tuple of (owner, repo, branch) or None if invalid
        """
        for pattern in self.GITHUB_URL_PATTERNS:
            match = pattern.match(url)
            if match:
                groups = match.groups()
                owner = groups[0]
                repo = groups[1].rstrip("/")
                branch = groups[2] if len(groups) > 2 else None
                return owner, repo, branch
        return None

    def validate_url(self, url: str) -> bool:
        """Check if a URL is a valid GitHub repository URL.

        Args:
            url: URL to validate

        Returns:
            True if valid GitHub URL
        """
        return self.parse_github_url(url) is not None

    def analyze_repository(
        self,
        repo_url: str,
        branch: str = "main",
        access_token: str | None = None,
    ) -> ImportSession:
        """Clone and analyze a GitHub repository.

        Args:
            repo_url: GitHub repository URL
            branch: Branch to clone (default: main)
            access_token: Optional access token for private repos

        Returns:
            ImportSession with analysis results

        Raises:
            InvalidRepositoryError: If URL is invalid or repo inaccessible
            AnalysisError: If analysis fails
            GitHubImportError: If GitPython is not installed
        """
        # Check if GitPython is available
        if not GIT_AVAILABLE:
            raise GitHubImportError(
                "GitPython is not installed. Install with: pip install gitpython"
            )

        # Validate URL
        if not self.validate_url(repo_url):
            raise InvalidRepositoryError(f"Invalid GitHub URL: {repo_url}")

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="mellea-import-"))
        logger.info(f"Cloning repository to {temp_dir}")

        try:
            # Clone repository
            clone_url = repo_url
            if access_token:
                # Insert token into URL for authentication
                clone_url = repo_url.replace(
                    "https://github.com",
                    f"https://{access_token}@github.com",
                )

            repo = Repo.clone_from(
                clone_url,
                temp_dir,
                branch=branch,
                depth=1,  # Shallow clone for speed
            )
            commit_sha = repo.head.commit.hexsha

            logger.info(f"Cloned repository at commit {commit_sha}")

            # Analyze the repository
            analysis = self._analyze_directory(temp_dir)

            # Create session
            session_id = str(uuid4())
            session = ImportSession(
                session_id=session_id,
                repo_url=repo_url,
                branch=branch,
                commit_sha=commit_sha,
                temp_dir=temp_dir,
                analysis=analysis,
            )
            self._sessions[session_id] = session

            logger.info(f"Created import session {session_id}")
            return session

        except GitCommandError as e:
            # Clean up on failure
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise InvalidRepositoryError(f"Failed to clone repository: {e}") from e
        except Exception as e:
            # Clean up on failure
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise AnalysisError(f"Analysis failed: {e}") from e

    def _analyze_directory(self, root: Path) -> AnalysisResult:
        """Analyze a directory for Python projects.

        Args:
            root: Root directory to analyze

        Returns:
            AnalysisResult with detected projects and dependencies
        """
        # List root files
        root_files = [
            f.name + ("/" if f.is_dir() else "")
            for f in sorted(root.iterdir())
            if not f.name.startswith(".")
        ]

        # Find Python projects
        python_projects = self._find_python_projects(root)

        # Get overall stats
        repo_size = self._get_dir_size(root)
        file_count = self._count_files(root)

        # Analyze primary project (highest confidence)
        detected_deps = None
        detected_slots: list[SlotMetadata] = []

        if python_projects:
            primary = max(python_projects, key=lambda p: p.confidence)
            project_path = root / primary.path if primary.path != "." else root

            detected_deps = self._extract_dependencies(project_path)
            detected_slots = self._detect_slots(project_path, root)

        return AnalysisResult(
            root_files=root_files,
            python_projects=python_projects,
            detected_dependencies=detected_deps,
            detected_slots=detected_slots,
            repo_size=repo_size,
            file_count=file_count,
        )

    def _find_python_projects(self, root: Path) -> list[PythonProject]:
        """Find Python project roots in a directory.

        Args:
            root: Root directory to search

        Returns:
            List of detected Python projects
        """
        projects: list[PythonProject] = []

        # Check root first
        root_indicators = self._get_project_indicators(root)
        if root_indicators:
            projects.append(
                PythonProject(
                    path=".",
                    entrypoint=self._detect_entrypoint(root),
                    confidence=0.9 if "pyproject.toml" in root_indicators else 0.7,
                    indicators=root_indicators,
                )
            )

        # Check immediate subdirectories
        for subdir in root.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("."):
                indicators = self._get_project_indicators(subdir)
                if indicators:
                    projects.append(
                        PythonProject(
                            path=subdir.name,
                            entrypoint=self._detect_entrypoint(subdir),
                            confidence=0.6,
                            indicators=indicators,
                        )
                    )

        return projects

    def _get_project_indicators(self, path: Path) -> list[str]:
        """Get list of project indicator files present in a directory.

        Args:
            path: Directory to check

        Returns:
            List of indicator files found
        """
        return [ind for ind in self.PROJECT_INDICATORS if (path / ind).exists()]

    def _detect_entrypoint(self, path: Path) -> str | None:
        """Find the likely entrypoint script in a directory.

        Args:
            path: Directory to search

        Returns:
            Relative path to entrypoint or None
        """
        for candidate in self.ENTRYPOINT_CANDIDATES:
            if (path / candidate).exists():
                return candidate

        # Fall back to first .py file in root
        py_files = list(path.glob("*.py"))
        if py_files:
            return py_files[0].name

        return None

    def _extract_dependencies(self, path: Path) -> DependencySpec:
        """Extract dependencies from a Python project.

        Args:
            path: Project directory

        Returns:
            DependencySpec with extracted packages
        """
        packages: list[PackageRef] = []
        source = DependencySource.MANUAL
        python_version: str | None = None

        # Try pyproject.toml first
        pyproject_path = path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                deps, py_ver = self._parse_pyproject(pyproject_path)
                packages.extend(deps)
                python_version = py_ver
                source = DependencySource.PYPROJECT
            except Exception as e:
                logger.warning(f"Failed to parse pyproject.toml: {e}")

        # Fall back to requirements.txt
        if not packages:
            requirements_path = path / "requirements.txt"
            if requirements_path.exists():
                try:
                    packages = self._parse_requirements(requirements_path)
                    source = DependencySource.REQUIREMENTS
                except Exception as e:
                    logger.warning(f"Failed to parse requirements.txt: {e}")

        return DependencySpec(
            source=source,
            packages=packages,
            pythonVersion=python_version,
        )

    def _parse_pyproject(self, path: Path) -> tuple[list[PackageRef], str | None]:
        """Parse pyproject.toml for dependencies.

        Args:
            path: Path to pyproject.toml

        Returns:
            Tuple of (packages, python_version)
        """
        import tomllib

        content = path.read_text()
        data = tomllib.loads(content)

        packages: list[PackageRef] = []
        python_version: str | None = None

        # Get dependencies from [project] section
        project = data.get("project", {})

        # Python version
        python_version = project.get("requires-python")

        # Dependencies
        deps = project.get("dependencies", [])
        for dep in deps:
            pkg = self._parse_dependency_string(dep)
            if pkg:
                packages.append(pkg)

        return packages, python_version

    def _parse_requirements(self, path: Path) -> list[PackageRef]:
        """Parse requirements.txt for dependencies.

        Args:
            path: Path to requirements.txt

        Returns:
            List of package references
        """
        packages: list[PackageRef] = []
        content = path.read_text()

        for line in content.splitlines():
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Skip options like -e, -r, etc.
            if line.startswith("-"):
                continue

            pkg = self._parse_dependency_string(line)
            if pkg:
                packages.append(pkg)

        return packages

    def _parse_dependency_string(self, dep: str) -> PackageRef | None:
        """Parse a dependency string into a PackageRef.

        Args:
            dep: Dependency string like "package>=1.0.0" or "package[extra]>=1.0"

        Returns:
            PackageRef or None if unparseable
        """
        # Pattern: package_name[extras]version_spec
        pattern = re.compile(
            r"^([a-zA-Z0-9_-]+)"  # Package name
            r"(?:\[([^\]]+)\])?"  # Optional extras
            r"(.*)$"  # Version spec
        )
        match = pattern.match(dep.strip())
        if not match:
            return None

        name = match.group(1)
        extras_str = match.group(2)
        version = match.group(3).strip() or None

        extras = extras_str.split(",") if extras_str else []

        return PackageRef(name=name, version=version, extras=extras)

    def _detect_slots(self, project_path: Path, workspace_root: Path) -> list[SlotMetadata]:
        """Detect @generative slots in Python files.

        Args:
            project_path: Project directory
            workspace_root: Root directory for relative paths

        Returns:
            List of detected slot metadata
        """
        slots: list[SlotMetadata] = []

        for py_file in project_path.rglob("*.py"):
            # Skip hidden directories
            if any(part.startswith(".") for part in py_file.parts):
                continue

            try:
                file_slots = self._analyze_file_for_slots(py_file, workspace_root)
                slots.extend(file_slots)
            except Exception as e:
                logger.warning(f"Failed to analyze {py_file}: {e}")

        return slots

    def _analyze_file_for_slots(
        self, file_path: Path, workspace_root: Path
    ) -> list[SlotMetadata]:
        """Analyze a Python file for @generative slots.

        Args:
            file_path: Path to Python file
            workspace_root: Root directory for relative paths

        Returns:
            List of slot metadata found in file
        """
        slots: list[SlotMetadata] = []

        source = file_path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = self._get_decorator_names(node)

                if "generative" in decorators:
                    relative_path = str(file_path.relative_to(workspace_root))
                    qualified_name = self._get_qualified_name(relative_path, node.name)

                    slots.append(
                        SlotMetadata(
                            name=node.name,
                            qualifiedName=qualified_name,
                            docstring=ast.get_docstring(node),
                            signature=self._extract_signature(node),
                            decorators=[f"@{d}" for d in decorators],
                            sourceFile=relative_path,
                            lineNumber=node.lineno,
                        )
                    )

        return slots

    def _get_decorator_names(self, func: ast.FunctionDef) -> list[str]:
        """Extract decorator names from a function definition.

        Args:
            func: AST function definition

        Returns:
            List of decorator names
        """
        names: list[str] = []

        for decorator in func.decorator_list:
            if isinstance(decorator, ast.Name):
                names.append(decorator.id)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    names.append(decorator.func.id)
                elif isinstance(decorator.func, ast.Attribute):
                    names.append(decorator.func.attr)

        return names

    def _get_qualified_name(self, file_path: str, func_name: str) -> str:
        """Generate qualified name for a function.

        Args:
            file_path: Relative file path
            func_name: Function name

        Returns:
            Qualified name like "src.module.function"
        """
        # Convert path to module-style name
        module_path = file_path.replace("/", ".").replace("\\", ".")
        if module_path.endswith(".py"):
            module_path = module_path[:-3]

        return f"{module_path}.{func_name}"

    def _extract_signature(self, func: ast.FunctionDef) -> SlotSignature:
        """Extract typed signature from a function definition.

        Args:
            func: AST function definition

        Returns:
            SlotSignature with args and return type
        """
        args: list[dict[str, Any]] = []

        for arg in func.args.args:
            if arg.arg == "self":
                continue

            arg_type = "Any"
            if arg.annotation:
                arg_type = self._annotation_to_string(arg.annotation)

            args.append(
                {
                    "name": arg.arg,
                    "type": arg_type,
                }
            )

        return_type: dict[str, Any] | None = None
        if func.returns:
            return_type = {"type": self._annotation_to_string(func.returns)}

        return SlotSignature(
            name=func.name,
            args=args,
            returns=return_type,
        )

    def _annotation_to_string(self, annotation: ast.expr) -> str:
        """Convert an AST annotation to string representation.

        Args:
            annotation: AST expression for type annotation

        Returns:
            String representation of the type
        """
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Subscript):
            base = self._annotation_to_string(annotation.value)
            if isinstance(annotation.slice, ast.Tuple):
                args = ", ".join(
                    self._annotation_to_string(a) for a in annotation.slice.elts
                )
            else:
                args = self._annotation_to_string(annotation.slice)
            return f"{base}[{args}]"
        else:
            return ast.unparse(annotation)

    def _get_dir_size(self, path: Path) -> int:
        """Get total size of a directory in bytes.

        Args:
            path: Directory path

        Returns:
            Total size in bytes
        """
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total

    def _count_files(self, path: Path) -> int:
        """Count files in a directory.

        Args:
            path: Directory path

        Returns:
            Number of files
        """
        return sum(1 for f in path.rglob("*") if f.is_file())

    def get_session(self, session_id: str) -> ImportSession | None:
        """Get an import session by ID.

        Args:
            session_id: Session ID

        Returns:
            ImportSession or None if not found
        """
        return self._sessions.get(session_id)

    def confirm_import(
        self,
        session_id: str,
        selected_path: str,
        name: str,
        description: str,
        entrypoint: str | None = None,
        tags: list[str] | None = None,
        owner: str = "",
    ) -> ProgramAsset:
        """Confirm and complete the import from a session.

        Args:
            session_id: Import session ID
            selected_path: Selected project path within repo
            name: Program name
            description: Program description
            entrypoint: Override entrypoint (uses detected if not provided)
            tags: Program tags
            owner: Owner user ID

        Returns:
            Created ProgramAsset

        Raises:
            SessionNotFoundError: If session not found
            GitHubImportError: If import fails
        """
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        try:
            # Find the selected project
            project = next(
                (p for p in session.analysis.python_projects if p.path == selected_path),
                None,
            )

            # Determine entrypoint
            final_entrypoint = entrypoint
            if not final_entrypoint and project:
                final_entrypoint = project.entrypoint
            if not final_entrypoint:
                final_entrypoint = "main.py"

            # Determine dependencies
            deps = session.analysis.detected_dependencies or DependencySpec(
                source=DependencySource.MANUAL
            )

            # Create the program
            program = ProgramAsset(
                name=name,
                description=description,
                tags=tags or ["imported", "github"],
                owner=owner,
                entrypoint=final_entrypoint,
                projectRoot="",  # Will be set after workspace creation
                dependencies=deps,
                exportedSlots=session.analysis.detected_slots,
            )

            created = self.asset_service.create_program(program)
            created.project_root = f"workspaces/{created.id}"

            # Copy files from temp directory to workspace
            source_dir = session.temp_dir
            if selected_path != ".":
                source_dir = session.temp_dir / selected_path

            self._copy_files_to_workspace(source_dir, created.id)

            # Update program with project root
            self.asset_service.update_program(created.id, created)

            logger.info(f"Imported program {created.id} from {session.repo_url}")

            # Clean up session
            self._cleanup_session(session_id)

            return created

        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise GitHubImportError(f"Import failed: {e}") from e

    def _copy_files_to_workspace(self, source_dir: Path, program_id: str) -> None:
        """Copy files from source directory to program workspace.

        Args:
            source_dir: Source directory to copy from
            program_id: Target program ID
        """
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                # Skip hidden files and directories
                if any(part.startswith(".") for part in file_path.parts):
                    continue

                relative_path = file_path.relative_to(source_dir)
                try:
                    content = file_path.read_text(encoding="utf-8")
                    self.asset_service.write_workspace_file(
                        program_id, str(relative_path), content
                    )
                except UnicodeDecodeError:
                    # Skip binary files for now
                    logger.warning(f"Skipping binary file: {relative_path}")

    def _cleanup_session(self, session_id: str) -> None:
        """Clean up an import session.

        Args:
            session_id: Session ID to clean up
        """
        session = self._sessions.pop(session_id, None)
        if session:
            shutil.rmtree(session.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up session {session_id}")

    def cancel_session(self, session_id: str) -> bool:
        """Cancel and clean up an import session.

        Args:
            session_id: Session ID to cancel

        Returns:
            True if session was found and cancelled
        """
        if session_id in self._sessions:
            self._cleanup_session(session_id)
            return True
        return False


# Global service instance
_github_import_service: GitHubImportService | None = None


def get_github_import_service() -> GitHubImportService:
    """Get the global GitHub import service instance."""
    global _github_import_service
    if _github_import_service is None:
        _github_import_service = GitHubImportService()
    return _github_import_service
