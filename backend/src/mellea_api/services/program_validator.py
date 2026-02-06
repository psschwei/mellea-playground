"""Program validation service with AST-based slot detection and dependency parsing."""

import ast
import logging
import re
from pathlib import Path
from typing import Any

from mellea_api.models.assets import (
    DependencySpec,
    PackageRef,
    SlotMetadata,
    SlotSignature,
)
from mellea_api.models.common import DependencySource

logger = logging.getLogger(__name__)


class ProgramValidator:
    """Service for validating and analyzing Python programs.

    Provides AST-based analysis for:
    - Detecting @generative slots
    - Extracting function signatures
    - Parsing dependencies from pyproject.toml and requirements.txt
    - Finding entrypoints

    This service is used by both GitHubImportService and ArchiveUploadService.
    """

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

    # Mellea decorators to detect (mellea 0.3.0)
    # Note: @generative is the primary decorator for defining generative slots
    MELLEA_DECORATORS = ["generative"]

    def detect_entrypoint(self, project_path: Path) -> str | None:
        """Find the likely entrypoint script in a directory.

        Args:
            project_path: Directory to search

        Returns:
            Relative path to entrypoint or None
        """
        for candidate in self.ENTRYPOINT_CANDIDATES:
            if (project_path / candidate).exists():
                return candidate

        # Fall back to first .py file in root
        py_files = list(project_path.glob("*.py"))
        if py_files:
            return py_files[0].name

        return None

    def extract_dependencies(self, project_path: Path) -> DependencySpec:
        """Extract dependencies from a Python project.

        Tries pyproject.toml first, then falls back to requirements.txt.

        Args:
            project_path: Project directory

        Returns:
            DependencySpec with extracted packages
        """
        packages: list[PackageRef] = []
        source = DependencySource.MANUAL
        python_version: str | None = None

        # Try pyproject.toml first
        pyproject_path = project_path / "pyproject.toml"
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
            requirements_path = project_path / "requirements.txt"
            if requirements_path.exists():
                try:
                    packages = self.parse_requirements(requirements_path)
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
            Tuple of (packages, pythonVersion)
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
            pkg = self.parse_dependency_string(dep)
            if pkg:
                packages.append(pkg)

        # Also check optional dependencies
        optional_deps = project.get("optional-dependencies", {})
        for _group, group_deps in optional_deps.items():
            for dep in group_deps:
                pkg = self.parse_dependency_string(dep)
                if pkg:
                    packages.append(pkg)

        return packages, python_version

    def parse_requirements(self, path: Path) -> list[PackageRef]:
        """Parse requirements.txt for dependencies.

        Handles:
        - Basic package names: requests
        - Version specifiers: requests>=2.28.0
        - Extras: requests[security]>=2.28.0
        - Comments: # this is a comment
        - Inline comments: requests>=2.28.0  # HTTP library
        - Options: -e, -r, --index-url, etc.
        - Environment markers: requests>=2.28.0; pythonVersion >= "3.8"
        - URL-based installs: git+https://...

        Args:
            path: Path to requirements.txt

        Returns:
            List of package references
        """
        packages: list[PackageRef] = []
        content = path.read_text()

        for line in content.splitlines():
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip full-line comments
            if line.startswith("#"):
                continue

            # Skip options like -e, -r, --index-url, etc.
            if line.startswith("-"):
                continue

            # Skip URL-based installs (git+, http://, https://)
            if line.startswith(("git+", "http://", "https://", "svn+", "hg+")):
                continue

            # Remove inline comments
            if " #" in line:
                line = line.split(" #")[0].strip()

            # Remove environment markers (everything after ;)
            if ";" in line:
                line = line.split(";")[0].strip()

            # Skip if empty after processing
            if not line:
                continue

            pkg = self.parse_dependency_string(line)
            if pkg:
                packages.append(pkg)

        return packages

    def parse_dependency_string(self, dep: str) -> PackageRef | None:
        """Parse a dependency string into a PackageRef.

        Handles various formats:
        - package
        - package==1.0.0
        - package>=1.0.0,<2.0.0
        - package[extra1,extra2]>=1.0.0
        - package @ https://...

        Args:
            dep: Dependency string

        Returns:
            PackageRef or None if unparseable
        """
        # Handle URL-based dependencies (package @ url)
        if " @ " in dep:
            name = dep.split(" @ ")[0].strip()
            # Remove extras from name if present
            if "[" in name:
                name = name.split("[")[0]
            return PackageRef(name=name, version=None, extras=[])

        # Pattern: package_name[extras]version_spec
        # More robust pattern that handles various version specifiers
        pattern = re.compile(
            r"^([a-zA-Z0-9][-a-zA-Z0-9_.]*)"  # Package name (PEP 508)
            r"(?:\[([^\]]+)\])?"  # Optional extras
            r"(.*)$"  # Version spec (can be complex like >=1.0,<2.0)
        )
        match = pattern.match(dep.strip())
        if not match:
            return None

        name = match.group(1)
        extras_str = match.group(2)
        version = match.group(3).strip() or None

        extras = [e.strip() for e in extras_str.split(",")] if extras_str else []

        return PackageRef(name=name, version=version, extras=extras)

    def detect_slots(self, project_path: Path) -> list[SlotMetadata]:
        """Detect @generative slots in Python files.

        Args:
            project_path: Project directory

        Returns:
            List of detected slot metadata
        """
        slots: list[SlotMetadata] = []

        for py_file in project_path.rglob("*.py"):
            # Skip hidden directories
            if any(part.startswith(".") for part in py_file.parts):
                continue

            try:
                file_slots = self._analyze_file_for_slots(py_file, project_path)
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

        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Failed to read {file_path}: not UTF-8 encoded")
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
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
            elif isinstance(decorator, ast.Attribute):
                names.append(decorator.attr)

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

    def validate_python_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Validate Python source code syntax.

        Args:
            source_code: Python source code string

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            ast.parse(source_code)
            return True, None
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

    def analyze_source_code(self, source_code: str, filename: str = "main.py") -> dict[str, Any]:
        """Analyze Python source code without files.

        Args:
            source_code: Python source code string
            filename: Virtual filename for qualified names

        Returns:
            Dict with analysis results including slots and syntax validity
        """
        # Check syntax
        is_valid, error = self.validate_python_syntax(source_code)
        if not is_valid:
            return {
                "valid": False,
                "error": error,
                "slots": [],
            }

        # Parse and analyze
        try:
            tree = ast.parse(source_code)
            slots: list[SlotMetadata] = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    decorators = self._get_decorator_names(node)

                    if "generative" in decorators:
                        qualified_name = self._get_qualified_name(filename, node.name)

                        slots.append(
                            SlotMetadata(
                                name=node.name,
                                qualifiedName=qualified_name,
                                docstring=ast.get_docstring(node),
                                signature=self._extract_signature(node),
                                decorators=[f"@{d}" for d in decorators],
                                sourceFile=filename,
                                lineNumber=node.lineno,
                            )
                        )

            return {
                "valid": True,
                "error": None,
                "slots": slots,
            }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "slots": [],
            }


# Global service instance
_program_validator: ProgramValidator | None = None


def get_program_validator() -> ProgramValidator:
    """Get the global program validator instance."""
    global _program_validator
    if _program_validator is None:
        _program_validator = ProgramValidator()
    return _program_validator
