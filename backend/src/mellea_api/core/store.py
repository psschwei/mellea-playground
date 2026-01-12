"""Thread-safe JSON storage with RLock for atomic operations."""

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonStore(Generic[T]):
    """Thread-safe JSON file storage with atomic read/write operations.

    Provides CRUD operations on a JSON file containing a list of Pydantic models.
    Uses RLock for thread-safety, allowing nested locks from the same thread.

    Example:
        ```python
        store = JsonStore[ProgramAsset](
            file_path=Path("data/metadata/programs.json"),
            collection_key="programs",
            model_class=ProgramAsset,
        )
        programs = store.list_all()
        store.create(new_program)
        ```
    """

    def __init__(
        self,
        file_path: Path,
        collection_key: str,
        model_class: type[T],
    ) -> None:
        """Initialize the JSON store.

        Args:
            file_path: Path to the JSON file
            collection_key: Key in the JSON object containing the list (e.g., "programs")
            model_class: Pydantic model class for serialization/deserialization
        """
        self.file_path = file_path
        self.collection_key = collection_key
        self.model_class = model_class
        self._lock = threading.RLock()

        # Ensure file exists with empty collection
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the JSON file with empty collection if it doesn't exist."""
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_raw({self.collection_key: []})

    def _read_raw(self) -> dict[str, Any]:
        """Read raw JSON data from file."""
        with open(self.file_path, encoding="utf-8") as f:
            return json.load(f)

    def _write_raw(self, data: dict[str, Any]) -> None:
        """Write raw JSON data to file atomically."""
        # Write to temp file first, then rename for atomicity
        temp_path = self.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        temp_path.replace(self.file_path)

    def list_all(self) -> list[T]:
        """List all items in the collection.

        Returns:
            List of all items as Pydantic models
        """
        with self._lock:
            data = self._read_raw()
            items = data.get(self.collection_key, [])
            return [self.model_class.model_validate(item) for item in items]

    def get_by_id(self, item_id: str) -> T | None:
        """Get an item by its ID.

        Args:
            item_id: The item's unique identifier

        Returns:
            The item if found, None otherwise
        """
        with self._lock:
            items = self.list_all()
            for item in items:
                if getattr(item, "id", None) == item_id:
                    return item
            return None

    def create(self, item: T) -> T:
        """Create a new item in the collection.

        Args:
            item: The item to create

        Returns:
            The created item

        Raises:
            ValueError: If an item with the same ID already exists
        """
        with self._lock:
            items = self.list_all()
            item_id = getattr(item, "id", None)

            # Check for duplicate ID
            if item_id and any(getattr(i, "id", None) == item_id for i in items):
                raise ValueError(f"Item with ID '{item_id}' already exists")

            items.append(item)
            self._write_collection(items)
            return item

    def update(self, item_id: str, item: T) -> T | None:
        """Update an existing item.

        Args:
            item_id: The ID of the item to update
            item: The updated item data

        Returns:
            The updated item if found, None otherwise
        """
        with self._lock:
            items = self.list_all()
            for i, existing in enumerate(items):
                if getattr(existing, "id", None) == item_id:
                    # Update the updatedAt timestamp if the model has it
                    if hasattr(item, "updated_at"):
                        object.__setattr__(item, "updated_at", datetime.utcnow())
                    items[i] = item
                    self._write_collection(items)
                    return item
            return None

    def delete(self, item_id: str) -> bool:
        """Delete an item by ID.

        Args:
            item_id: The ID of the item to delete

        Returns:
            True if the item was deleted, False if not found
        """
        with self._lock:
            items = self.list_all()
            original_len = len(items)
            items = [i for i in items if getattr(i, "id", None) != item_id]

            if len(items) < original_len:
                self._write_collection(items)
                return True
            return False

    def find(self, predicate: Any) -> list[T]:
        """Find items matching a predicate function.

        Args:
            predicate: A function that takes an item and returns True if it matches

        Returns:
            List of matching items
        """
        with self._lock:
            items = self.list_all()
            return [item for item in items if predicate(item)]

    def count(self) -> int:
        """Get the number of items in the collection."""
        with self._lock:
            data = self._read_raw()
            return len(data.get(self.collection_key, []))

    def _write_collection(self, items: list[T]) -> None:
        """Write the collection back to the JSON file."""
        data = {
            self.collection_key: [
                item.model_dump(mode="json", by_alias=True) for item in items
            ]
        }
        self._write_raw(data)

    def clear(self) -> int:
        """Remove all items from the collection.

        Returns:
            Number of items removed
        """
        with self._lock:
            count = self.count()
            self._write_raw({self.collection_key: []})
            return count

    def backup(self, backup_path: Path | None = None) -> Path:
        """Create a backup of the JSON file.

        Args:
            backup_path: Optional custom backup path

        Returns:
            Path to the backup file
        """
        with self._lock:
            if backup_path is None:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_path = self.file_path.with_suffix(f".{timestamp}.backup.json")
            shutil.copy2(self.file_path, backup_path)
            return backup_path
