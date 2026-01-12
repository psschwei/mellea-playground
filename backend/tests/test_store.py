"""Tests for JsonStore."""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from mellea_api.core.store import JsonStore


class SampleItem(BaseModel):
    """Sample model for testing."""

    id: str
    name: str
    value: int = 0


@pytest.fixture
def temp_store() -> Iterator[JsonStore[SampleItem]]:
    """Create a temporary JsonStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "items.json"
        yield JsonStore[SampleItem](
            file_path=file_path,
            collection_key="items",
            model_class=SampleItem,
        )


def test_create_and_list(temp_store: JsonStore[SampleItem]) -> None:
    """Test creating and listing items."""
    item = SampleItem(id="1", name="test", value=42)
    created = temp_store.create(item)

    assert created.id == "1"
    assert created.name == "test"

    items = temp_store.list_all()
    assert len(items) == 1
    assert items[0].id == "1"


def test_get_by_id(temp_store: JsonStore[SampleItem]) -> None:
    """Test getting an item by ID."""
    item = SampleItem(id="abc", name="test")
    temp_store.create(item)

    found = temp_store.get_by_id("abc")
    assert found is not None
    assert found.name == "test"

    not_found = temp_store.get_by_id("xyz")
    assert not_found is None


def test_update(temp_store: JsonStore[SampleItem]) -> None:
    """Test updating an item."""
    item = SampleItem(id="1", name="original", value=10)
    temp_store.create(item)

    updated_item = SampleItem(id="1", name="updated", value=20)
    result = temp_store.update("1", updated_item)

    assert result is not None
    assert result.name == "updated"
    assert result.value == 20

    # Verify persistence
    found = temp_store.get_by_id("1")
    assert found is not None
    assert found.name == "updated"


def test_delete(temp_store: JsonStore[SampleItem]) -> None:
    """Test deleting an item."""
    item = SampleItem(id="1", name="test")
    temp_store.create(item)

    assert temp_store.count() == 1

    deleted = temp_store.delete("1")
    assert deleted is True
    assert temp_store.count() == 0

    # Try deleting non-existent item
    not_deleted = temp_store.delete("xyz")
    assert not_deleted is False


def test_duplicate_id_raises(temp_store: JsonStore[SampleItem]) -> None:
    """Test that creating an item with duplicate ID raises an error."""
    item1 = SampleItem(id="1", name="first")
    temp_store.create(item1)

    item2 = SampleItem(id="1", name="second")
    with pytest.raises(ValueError, match="already exists"):
        temp_store.create(item2)


def test_find(temp_store: JsonStore[SampleItem]) -> None:
    """Test finding items with a predicate."""
    temp_store.create(SampleItem(id="1", name="alpha", value=10))
    temp_store.create(SampleItem(id="2", name="beta", value=20))
    temp_store.create(SampleItem(id="3", name="alpha", value=30))

    results = temp_store.find(lambda x: x.name == "alpha")
    assert len(results) == 2
    assert all(r.name == "alpha" for r in results)


def test_clear(temp_store: JsonStore[SampleItem]) -> None:
    """Test clearing all items."""
    temp_store.create(SampleItem(id="1", name="a"))
    temp_store.create(SampleItem(id="2", name="b"))
    temp_store.create(SampleItem(id="3", name="c"))

    assert temp_store.count() == 3

    cleared = temp_store.clear()
    assert cleared == 3
    assert temp_store.count() == 0
