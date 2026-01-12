"""Tests for AssetService."""

import tempfile
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.assets import (
    CompositionAsset,
    DependencySpec,
    ModelAsset,
    ModelParams,
    ProgramAsset,
)
from mellea_api.models.common import DependencySource, ModelProvider
from mellea_api.services.assets import (
    AssetAlreadyExistsError,
    AssetNotFoundError,
    AssetService,
    WorkspaceError,
)


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_data_dir: Path):
    """Create test settings with temporary data directory."""
    settings = Settings(data_dir=temp_data_dir)
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def service(settings: Settings):
    """Create an AssetService with test settings."""
    return AssetService(settings=settings)


@pytest.fixture
def sample_program():
    """Create a sample program asset."""
    return ProgramAsset(
        name="Test Program",
        owner="user-123",
        entrypoint="src/main.py",
        projectRoot="workspaces/test-prog",
        dependencies=DependencySpec(source=DependencySource.PYPROJECT),
        tags=["test", "sample"],
    )


@pytest.fixture
def sample_model():
    """Create a sample model asset."""
    return ModelAsset(
        name="Test Model",
        owner="user-123",
        provider=ModelProvider.OPENAI,
        modelId="gpt-4",
        defaultParams=ModelParams(temperature=0.7),
        tags=["test"],
    )


@pytest.fixture
def sample_composition():
    """Create a sample composition asset."""
    return CompositionAsset(
        name="Test Composition",
        owner="user-123",
        tags=["test"],
    )


class TestProgramOperations:
    """Tests for program CRUD operations."""

    def test_create_program(self, service: AssetService, sample_program: ProgramAsset):
        """Test creating a new program."""
        created = service.create_program(sample_program)

        assert created.id == sample_program.id
        assert created.name == "Test Program"
        assert created.owner == "user-123"

    def test_create_program_creates_workspace(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that creating a program also creates its workspace."""
        created = service.create_program(sample_program)

        workspace_path = service._get_workspace_path(created.id)
        assert workspace_path.exists()
        assert (workspace_path / "src").exists()

    def test_create_duplicate_program_raises_error(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that creating a duplicate program raises an error."""
        service.create_program(sample_program)

        with pytest.raises(AssetAlreadyExistsError):
            service.create_program(sample_program)

    def test_get_program(self, service: AssetService, sample_program: ProgramAsset):
        """Test getting a program by ID."""
        created = service.create_program(sample_program)

        fetched = service.get_program(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == created.name

    def test_get_nonexistent_program_returns_none(self, service: AssetService):
        """Test that getting a nonexistent program returns None."""
        result = service.get_program("nonexistent-id")
        assert result is None

    def test_list_programs(self, service: AssetService, sample_program: ProgramAsset):
        """Test listing all programs."""
        service.create_program(sample_program)

        programs = service.list_programs()

        assert len(programs) == 1
        assert programs[0].name == "Test Program"

    def test_list_programs_filter_by_owner(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test filtering programs by owner."""
        service.create_program(sample_program)

        # Create another program with different owner
        other_program = ProgramAsset(
            name="Other Program",
            owner="user-456",
            entrypoint="main.py",
            projectRoot="workspaces/other",
            dependencies=DependencySpec(source=DependencySource.MANUAL),
        )
        service.create_program(other_program)

        # Filter by owner
        programs = service.list_programs(owner="user-123")

        assert len(programs) == 1
        assert programs[0].owner == "user-123"

    def test_list_programs_filter_by_tags(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test filtering programs by tags."""
        service.create_program(sample_program)

        # Create another program with different tags
        other_program = ProgramAsset(
            name="Other Program",
            owner="user-123",
            entrypoint="main.py",
            projectRoot="workspaces/other",
            dependencies=DependencySpec(source=DependencySource.MANUAL),
            tags=["other"],
        )
        service.create_program(other_program)

        # Filter by tags
        programs = service.list_programs(tags=["test", "sample"])

        assert len(programs) == 1
        assert programs[0].name == "Test Program"

    def test_update_program(self, service: AssetService, sample_program: ProgramAsset):
        """Test updating a program."""
        created = service.create_program(sample_program)

        created.name = "Updated Program"
        updated = service.update_program(created.id, created)

        assert updated is not None
        assert updated.name == "Updated Program"

        # Verify persistence
        fetched = service.get_program(created.id)
        assert fetched is not None
        assert fetched.name == "Updated Program"

    def test_update_nonexistent_program_returns_none(self, service: AssetService):
        """Test that updating a nonexistent program returns None."""
        program = ProgramAsset(
            id="nonexistent",
            name="Test",
            owner="user-123",
            entrypoint="main.py",
            projectRoot="workspaces/test",
            dependencies=DependencySpec(source=DependencySource.MANUAL),
        )
        result = service.update_program("nonexistent", program)
        assert result is None

    def test_delete_program(self, service: AssetService, sample_program: ProgramAsset):
        """Test deleting a program."""
        created = service.create_program(sample_program)
        workspace_path = service._get_workspace_path(created.id)

        deleted = service.delete_program(created.id)

        assert deleted is True
        assert service.get_program(created.id) is None
        assert not workspace_path.exists()

    def test_delete_nonexistent_program_returns_false(self, service: AssetService):
        """Test that deleting a nonexistent program returns False."""
        result = service.delete_program("nonexistent-id")
        assert result is False


class TestModelOperations:
    """Tests for model CRUD operations."""

    def test_create_model(self, service: AssetService, sample_model: ModelAsset):
        """Test creating a new model."""
        created = service.create_model(sample_model)

        assert created.id == sample_model.id
        assert created.name == "Test Model"
        assert created.provider == ModelProvider.OPENAI

    def test_create_duplicate_model_raises_error(
        self, service: AssetService, sample_model: ModelAsset
    ):
        """Test that creating a duplicate model raises an error."""
        service.create_model(sample_model)

        with pytest.raises(AssetAlreadyExistsError):
            service.create_model(sample_model)

    def test_get_model(self, service: AssetService, sample_model: ModelAsset):
        """Test getting a model by ID."""
        created = service.create_model(sample_model)

        fetched = service.get_model(created.id)

        assert fetched is not None
        assert fetched.id == created.id

    def test_list_models_filter_by_provider(
        self, service: AssetService, sample_model: ModelAsset
    ):
        """Test filtering models by provider."""
        service.create_model(sample_model)

        # Create another model with different provider
        other_model = ModelAsset(
            name="Anthropic Model",
            owner="user-123",
            provider=ModelProvider.ANTHROPIC,
            modelId="claude-3",
            defaultParams=ModelParams(),
        )
        service.create_model(other_model)

        # Filter by provider
        models = service.list_models(provider=ModelProvider.OPENAI)

        assert len(models) == 1
        assert models[0].provider == ModelProvider.OPENAI

    def test_update_model(self, service: AssetService, sample_model: ModelAsset):
        """Test updating a model."""
        created = service.create_model(sample_model)

        created.name = "Updated Model"
        updated = service.update_model(created.id, created)

        assert updated is not None
        assert updated.name == "Updated Model"

    def test_delete_model(self, service: AssetService, sample_model: ModelAsset):
        """Test deleting a model."""
        created = service.create_model(sample_model)

        deleted = service.delete_model(created.id)

        assert deleted is True
        assert service.get_model(created.id) is None


class TestCompositionOperations:
    """Tests for composition CRUD operations."""

    def test_create_composition(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test creating a new composition."""
        created = service.create_composition(sample_composition)

        assert created.id == sample_composition.id
        assert created.name == "Test Composition"

    def test_create_duplicate_composition_raises_error(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test that creating a duplicate composition raises an error."""
        service.create_composition(sample_composition)

        with pytest.raises(AssetAlreadyExistsError):
            service.create_composition(sample_composition)

    def test_get_composition(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test getting a composition by ID."""
        created = service.create_composition(sample_composition)

        fetched = service.get_composition(created.id)

        assert fetched is not None
        assert fetched.id == created.id

    def test_list_compositions_filter_by_owner(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test filtering compositions by owner."""
        service.create_composition(sample_composition)

        # Create another composition with different owner
        other_composition = CompositionAsset(
            name="Other Composition",
            owner="user-456",
        )
        service.create_composition(other_composition)

        # Filter by owner
        compositions = service.list_compositions(owner="user-123")

        assert len(compositions) == 1
        assert compositions[0].owner == "user-123"

    def test_update_composition(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test updating a composition."""
        created = service.create_composition(sample_composition)

        created.name = "Updated Composition"
        updated = service.update_composition(created.id, created)

        assert updated is not None
        assert updated.name == "Updated Composition"

    def test_delete_composition(
        self, service: AssetService, sample_composition: CompositionAsset
    ):
        """Test deleting a composition."""
        created = service.create_composition(sample_composition)

        deleted = service.delete_composition(created.id)

        assert deleted is True
        assert service.get_composition(created.id) is None


class TestWorkspaceOperations:
    """Tests for workspace file operations."""

    def test_list_workspace_files(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test listing files in a workspace."""
        created = service.create_program(sample_program)

        # Write some files
        service.write_workspace_file(created.id, "src/main.py", "print('hello')")
        service.write_workspace_file(created.id, "README.md", "# Test")

        files = service.list_workspace_files(created.id)

        assert "src/main.py" in files
        assert "README.md" in files

    def test_list_workspace_files_nonexistent_workspace(self, service: AssetService):
        """Test that listing files in a nonexistent workspace raises an error."""
        with pytest.raises(AssetNotFoundError):
            service.list_workspace_files("nonexistent-id")

    def test_read_workspace_file(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test reading a file from a workspace."""
        created = service.create_program(sample_program)
        service.write_workspace_file(created.id, "test.txt", "Hello, World!")

        content = service.read_workspace_file(created.id, "test.txt")

        assert content == "Hello, World!"

    def test_read_nonexistent_file_raises_error(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that reading a nonexistent file raises an error."""
        created = service.create_program(sample_program)

        with pytest.raises(AssetNotFoundError):
            service.read_workspace_file(created.id, "nonexistent.txt")

    def test_write_workspace_file(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test writing a file to a workspace."""
        created = service.create_program(sample_program)

        service.write_workspace_file(created.id, "new_file.py", "# New file")

        content = service.read_workspace_file(created.id, "new_file.py")
        assert content == "# New file"

    def test_write_workspace_file_creates_directories(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that writing a file creates necessary directories."""
        created = service.create_program(sample_program)

        service.write_workspace_file(
            created.id, "deeply/nested/dir/file.txt", "content"
        )

        content = service.read_workspace_file(
            created.id, "deeply/nested/dir/file.txt"
        )
        assert content == "content"

    def test_write_workspace_file_path_traversal_blocked(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that path traversal attacks are blocked."""
        created = service.create_program(sample_program)

        with pytest.raises(WorkspaceError):
            service.write_workspace_file(created.id, "../../../etc/passwd", "hack")

    def test_read_workspace_file_path_traversal_blocked(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that path traversal attacks are blocked on read."""
        created = service.create_program(sample_program)

        with pytest.raises(WorkspaceError):
            service.read_workspace_file(created.id, "../../../etc/passwd")

    def test_delete_workspace_file(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test deleting a file from a workspace."""
        created = service.create_program(sample_program)
        service.write_workspace_file(created.id, "to_delete.txt", "temp")

        deleted = service.delete_workspace_file(created.id, "to_delete.txt")

        assert deleted is True
        with pytest.raises(AssetNotFoundError):
            service.read_workspace_file(created.id, "to_delete.txt")

    def test_delete_nonexistent_file_returns_false(
        self, service: AssetService, sample_program: ProgramAsset
    ):
        """Test that deleting a nonexistent file returns False."""
        created = service.create_program(sample_program)

        deleted = service.delete_workspace_file(created.id, "nonexistent.txt")

        assert deleted is False


class TestSearchOperations:
    """Tests for search functionality."""

    def test_search_all_assets(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
        sample_model: ModelAsset,
        sample_composition: CompositionAsset,
    ):
        """Test searching all asset types."""
        service.create_program(sample_program)
        service.create_model(sample_model)
        service.create_composition(sample_composition)

        results = service.search()

        assert len(results) == 3

    def test_search_by_type(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
        sample_model: ModelAsset,
    ):
        """Test searching by asset type."""
        service.create_program(sample_program)
        service.create_model(sample_model)

        results = service.search(asset_type="program")

        assert len(results) == 1
        assert results[0].name == "Test Program"

    def test_search_by_query(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
        sample_model: ModelAsset,
    ):
        """Test searching by query string."""
        service.create_program(sample_program)
        service.create_model(sample_model)

        results = service.search(query="Program")

        assert len(results) == 1
        assert results[0].name == "Test Program"

    def test_search_by_owner(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
    ):
        """Test searching by owner."""
        service.create_program(sample_program)

        # Create another program with different owner
        other_program = ProgramAsset(
            name="Other Program",
            owner="user-456",
            entrypoint="main.py",
            projectRoot="workspaces/other",
            dependencies=DependencySpec(source=DependencySource.MANUAL),
        )
        service.create_program(other_program)

        results = service.search(owner="user-123")

        assert len(results) == 1
        assert results[0].owner == "user-123"

    def test_search_by_tags(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
    ):
        """Test searching by tags."""
        service.create_program(sample_program)

        # Create another program with different tags
        other_program = ProgramAsset(
            name="Other Program",
            owner="user-123",
            entrypoint="main.py",
            projectRoot="workspaces/other",
            dependencies=DependencySpec(source=DependencySource.MANUAL),
            tags=["other"],
        )
        service.create_program(other_program)

        results = service.search(tags=["test"])

        assert len(results) == 1
        assert "test" in results[0].tags

    def test_search_case_insensitive(
        self,
        service: AssetService,
        sample_program: ProgramAsset,
    ):
        """Test that search is case-insensitive."""
        service.create_program(sample_program)

        results = service.search(query="test program")

        assert len(results) == 1
        assert results[0].name == "Test Program"
