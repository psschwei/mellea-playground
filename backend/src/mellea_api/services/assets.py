"""Asset service for managing catalog assets (programs, models, compositions)."""

import logging
import os
import shutil
from pathlib import Path

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.assets import (
    AssetMetadata,
    CompositionAsset,
    ModelAsset,
    ProgramAsset,
)
from mellea_api.models.common import ModelProvider

logger = logging.getLogger(__name__)


class AssetNotFoundError(Exception):
    """Raised when an asset is not found."""

    pass


class AssetAlreadyExistsError(Exception):
    """Raised when creating an asset that already exists."""

    pass


class WorkspaceError(Exception):
    """Raised when workspace operations fail."""

    pass


class AssetService:
    """Service for managing catalog assets (programs, models, compositions).

    Provides CRUD operations for all asset types plus workspace file management
    for programs. Uses JsonStore for thread-safe persistence.

    Example:
        ```python
        service = get_asset_service()

        # Create a program
        program = ProgramAsset(
            name="My Program",
            owner="user-123",
            entrypoint="src/main.py",
            project_root="workspaces/prog-xxx",
            dependencies=DependencySpec(source=DependencySource.PYPROJECT),
        )
        created = service.create_program(program)

        # List all programs for a user
        programs = service.list_programs(owner="user-123")
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the asset service.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._program_store: JsonStore[ProgramAsset] | None = None
        self._model_store: JsonStore[ModelAsset] | None = None
        self._composition_store: JsonStore[CompositionAsset] | None = None

    # -------------------------------------------------------------------------
    # Store Properties (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def program_store(self) -> JsonStore[ProgramAsset]:
        """Get the program store, initializing if needed."""
        if self._program_store is None:
            file_path = self.settings.data_dir / "metadata" / "programs.json"
            self._program_store = JsonStore[ProgramAsset](
                file_path=file_path,
                collection_key="programs",
                model_class=ProgramAsset,
            )
        return self._program_store

    @property
    def model_store(self) -> JsonStore[ModelAsset]:
        """Get the model store, initializing if needed."""
        if self._model_store is None:
            file_path = self.settings.data_dir / "metadata" / "models.json"
            self._model_store = JsonStore[ModelAsset](
                file_path=file_path,
                collection_key="models",
                model_class=ModelAsset,
            )
        return self._model_store

    @property
    def composition_store(self) -> JsonStore[CompositionAsset]:
        """Get the composition store, initializing if needed."""
        if self._composition_store is None:
            file_path = self.settings.data_dir / "metadata" / "compositions.json"
            self._composition_store = JsonStore[CompositionAsset](
                file_path=file_path,
                collection_key="compositions",
                model_class=CompositionAsset,
            )
        return self._composition_store

    # -------------------------------------------------------------------------
    # Program Operations
    # -------------------------------------------------------------------------

    def list_programs(
        self,
        owner: str | None = None,
        tags: list[str] | None = None,
    ) -> list[ProgramAsset]:
        """List programs with optional filtering.

        Args:
            owner: Filter by owner ID
            tags: Filter by tags (must have all specified tags)

        Returns:
            List of matching programs
        """
        programs = self.program_store.list_all()

        if owner:
            programs = [p for p in programs if p.owner == owner]

        if tags:
            programs = [p for p in programs if all(t in p.tags for t in tags)]

        return programs

    def get_program(self, program_id: str) -> ProgramAsset | None:
        """Get a program by ID.

        Args:
            program_id: Program's unique identifier

        Returns:
            Program if found, None otherwise
        """
        return self.program_store.get_by_id(program_id)

    def create_program(self, program: ProgramAsset) -> ProgramAsset:
        """Create a new program.

        Also creates the workspace directory for the program.

        Args:
            program: Program to create

        Returns:
            Created program

        Raises:
            AssetAlreadyExistsError: If a program with the same ID exists
        """
        try:
            created = self.program_store.create(program)
            # Create workspace directory
            self.create_workspace(program.id)
            logger.info(f"Created program: {program.name} ({program.id})")
            return created
        except ValueError as e:
            raise AssetAlreadyExistsError(str(e)) from e

    def update_program(
        self, program_id: str, program: ProgramAsset
    ) -> ProgramAsset | None:
        """Update an existing program.

        Args:
            program_id: ID of the program to update
            program: Updated program data

        Returns:
            Updated program if found, None otherwise
        """
        result = self.program_store.update(program_id, program)
        if result:
            logger.info(f"Updated program: {program.name} ({program_id})")
        return result

    def delete_program(self, program_id: str) -> bool:
        """Delete a program and its workspace.

        Args:
            program_id: ID of the program to delete

        Returns:
            True if deleted, False if not found
        """
        deleted = self.program_store.delete(program_id)
        if deleted:
            # Also delete workspace
            self.delete_workspace(program_id)
            logger.info(f"Deleted program: {program_id}")
        return deleted

    # -------------------------------------------------------------------------
    # Model Operations
    # -------------------------------------------------------------------------

    def list_models(
        self,
        owner: str | None = None,
        provider: ModelProvider | None = None,
    ) -> list[ModelAsset]:
        """List models with optional filtering.

        Args:
            owner: Filter by owner ID
            provider: Filter by model provider

        Returns:
            List of matching models
        """
        models = self.model_store.list_all()

        if owner:
            models = [m for m in models if m.owner == owner]

        if provider:
            models = [m for m in models if m.provider == provider]

        return models

    def get_model(self, model_id: str) -> ModelAsset | None:
        """Get a model by ID.

        Args:
            model_id: Model's unique identifier

        Returns:
            Model if found, None otherwise
        """
        return self.model_store.get_by_id(model_id)

    def create_model(self, model: ModelAsset) -> ModelAsset:
        """Create a new model.

        Args:
            model: Model to create

        Returns:
            Created model

        Raises:
            AssetAlreadyExistsError: If a model with the same ID exists
        """
        try:
            created = self.model_store.create(model)
            logger.info(f"Created model: {model.name} ({model.id})")
            return created
        except ValueError as e:
            raise AssetAlreadyExistsError(str(e)) from e

    def update_model(self, model_id: str, model: ModelAsset) -> ModelAsset | None:
        """Update an existing model.

        Args:
            model_id: ID of the model to update
            model: Updated model data

        Returns:
            Updated model if found, None otherwise
        """
        result = self.model_store.update(model_id, model)
        if result:
            logger.info(f"Updated model: {model.name} ({model_id})")
        return result

    def delete_model(self, model_id: str) -> bool:
        """Delete a model.

        Args:
            model_id: ID of the model to delete

        Returns:
            True if deleted, False if not found
        """
        deleted = self.model_store.delete(model_id)
        if deleted:
            logger.info(f"Deleted model: {model_id}")
        return deleted

    # -------------------------------------------------------------------------
    # Composition Operations
    # -------------------------------------------------------------------------

    def list_compositions(
        self,
        owner: str | None = None,
    ) -> list[CompositionAsset]:
        """List compositions with optional filtering.

        Args:
            owner: Filter by owner ID

        Returns:
            List of matching compositions
        """
        compositions = self.composition_store.list_all()

        if owner:
            compositions = [c for c in compositions if c.owner == owner]

        return compositions

    def get_composition(self, composition_id: str) -> CompositionAsset | None:
        """Get a composition by ID.

        Args:
            composition_id: Composition's unique identifier

        Returns:
            Composition if found, None otherwise
        """
        return self.composition_store.get_by_id(composition_id)

    def create_composition(self, composition: CompositionAsset) -> CompositionAsset:
        """Create a new composition.

        Args:
            composition: Composition to create

        Returns:
            Created composition

        Raises:
            AssetAlreadyExistsError: If a composition with the same ID exists
        """
        try:
            created = self.composition_store.create(composition)
            logger.info(f"Created composition: {composition.name} ({composition.id})")
            return created
        except ValueError as e:
            raise AssetAlreadyExistsError(str(e)) from e

    def update_composition(
        self, composition_id: str, composition: CompositionAsset
    ) -> CompositionAsset | None:
        """Update an existing composition.

        Args:
            composition_id: ID of the composition to update
            composition: Updated composition data

        Returns:
            Updated composition if found, None otherwise
        """
        result = self.composition_store.update(composition_id, composition)
        if result:
            logger.info(f"Updated composition: {composition.name} ({composition_id})")
        return result

    def delete_composition(self, composition_id: str) -> bool:
        """Delete a composition.

        Args:
            composition_id: ID of the composition to delete

        Returns:
            True if deleted, False if not found
        """
        deleted = self.composition_store.delete(composition_id)
        if deleted:
            logger.info(f"Deleted composition: {composition_id}")
        return deleted

    # -------------------------------------------------------------------------
    # Workspace Operations (for Programs)
    # -------------------------------------------------------------------------

    def _get_workspace_path(self, program_id: str) -> Path:
        """Get the workspace directory path for a program."""
        return self.settings.data_dir / "workspaces" / program_id

    def create_workspace(self, program_id: str) -> Path:
        """Create a workspace directory for a program.

        Args:
            program_id: Program ID

        Returns:
            Path to the created workspace

        Raises:
            WorkspaceError: If workspace creation fails
        """
        workspace_path = self._get_workspace_path(program_id)
        try:
            workspace_path.mkdir(parents=True, exist_ok=True)
            # Create default structure
            (workspace_path / "src").mkdir(exist_ok=True)
            logger.info(f"Created workspace: {workspace_path}")
            return workspace_path
        except OSError as e:
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

    def delete_workspace(self, program_id: str) -> bool:
        """Delete a program's workspace directory.

        Args:
            program_id: Program ID

        Returns:
            True if deleted, False if not found
        """
        workspace_path = self._get_workspace_path(program_id)
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            logger.info(f"Deleted workspace: {workspace_path}")
            return True
        return False

    def list_workspace_files(self, program_id: str) -> list[str]:
        """List all files in a program's workspace.

        Args:
            program_id: Program ID

        Returns:
            List of relative file paths

        Raises:
            AssetNotFoundError: If workspace doesn't exist
        """
        workspace_path = self._get_workspace_path(program_id)
        if not workspace_path.exists():
            raise AssetNotFoundError(f"Workspace not found: {program_id}")

        files = []
        for root, _, filenames in os.walk(workspace_path):
            for filename in filenames:
                full_path = Path(root) / filename
                rel_path = full_path.relative_to(workspace_path)
                files.append(str(rel_path))

        return sorted(files)

    def read_workspace_file(self, program_id: str, path: str) -> str:
        """Read a file from a program's workspace.

        Args:
            program_id: Program ID
            path: Relative path within the workspace

        Returns:
            File contents as string

        Raises:
            AssetNotFoundError: If workspace or file doesn't exist
            WorkspaceError: If file cannot be read
        """
        workspace_path = self._get_workspace_path(program_id)
        if not workspace_path.exists():
            raise AssetNotFoundError(f"Workspace not found: {program_id}")

        file_path = workspace_path / path
        # Security: ensure path doesn't escape workspace
        try:
            file_path.resolve().relative_to(workspace_path.resolve())
        except ValueError as e:
            raise WorkspaceError(f"Invalid path: {path}") from e

        if not file_path.exists():
            raise AssetNotFoundError(f"File not found: {path}")

        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as e:
            raise WorkspaceError(f"Failed to read file: {e}") from e

    def write_workspace_file(self, program_id: str, path: str, content: str) -> None:
        """Write a file to a program's workspace.

        Args:
            program_id: Program ID
            path: Relative path within the workspace
            content: File contents

        Raises:
            AssetNotFoundError: If workspace doesn't exist
            WorkspaceError: If file cannot be written
        """
        workspace_path = self._get_workspace_path(program_id)
        if not workspace_path.exists():
            raise AssetNotFoundError(f"Workspace not found: {program_id}")

        file_path = workspace_path / path
        # Security: ensure path doesn't escape workspace
        try:
            file_path.resolve().relative_to(workspace_path.resolve())
        except ValueError as e:
            raise WorkspaceError(f"Invalid path: {path}") from e

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Wrote file: {file_path}")
        except OSError as e:
            raise WorkspaceError(f"Failed to write file: {e}") from e

    def delete_workspace_file(self, program_id: str, path: str) -> bool:
        """Delete a file from a program's workspace.

        Args:
            program_id: Program ID
            path: Relative path within the workspace

        Returns:
            True if deleted, False if not found

        Raises:
            AssetNotFoundError: If workspace doesn't exist
            WorkspaceError: If path is invalid
        """
        workspace_path = self._get_workspace_path(program_id)
        if not workspace_path.exists():
            raise AssetNotFoundError(f"Workspace not found: {program_id}")

        file_path = workspace_path / path
        # Security: ensure path doesn't escape workspace
        try:
            file_path.resolve().relative_to(workspace_path.resolve())
        except ValueError as e:
            raise WorkspaceError(f"Invalid path: {path}") from e

        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True
        return False

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str | None = None,
        asset_type: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
    ) -> list[AssetMetadata]:
        """Search across all asset types.

        Args:
            query: Text search in name and description
            asset_type: Filter by type ("program", "model", "composition")
            owner: Filter by owner ID
            tags: Filter by tags

        Returns:
            List of matching assets (as base AssetMetadata)
        """
        results: list[AssetMetadata] = []

        # Collect assets based on type filter
        if asset_type is None or asset_type == "program":
            results.extend(self.program_store.list_all())

        if asset_type is None or asset_type == "model":
            results.extend(self.model_store.list_all())

        if asset_type is None or asset_type == "composition":
            results.extend(self.composition_store.list_all())

        # Apply filters
        if owner:
            results = [r for r in results if r.owner == owner]

        if tags:
            results = [r for r in results if all(t in r.tags for t in tags)]

        if query:
            query_lower = query.lower()
            results = [
                r
                for r in results
                if query_lower in r.name.lower()
                or query_lower in r.description.lower()
            ]

        return results


# Global service instance
_asset_service: AssetService | None = None


def get_asset_service() -> AssetService:
    """Get the global asset service instance."""
    global _asset_service
    if _asset_service is None:
        _asset_service = AssetService()
    return _asset_service
