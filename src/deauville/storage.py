import json
import os
import tempfile
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path

from deauville.errors import (
    FestivalError,
    InvalidValueError,
    NotFoundError,
    StorageError,
)
from deauville.festival import Festival
from deauville.models import (
    Artist,
    Lineup,
    Performance,
    SoloShow,
    Venue,
    Workshop,
    parse_day,
    parse_moment,
)


# E11 - A real package
class FestivalStorage(ABC):
    """Replaceable persistence boundary used by the terminal and API."""

    @abstractmethod
    def load(self) -> Festival:
        """Load a fresh festival and validate all its rules."""

    @abstractmethod
    def save(self, festival: Festival) -> None:
        """Persist a validated festival or raise StorageError."""


def performance_from_data(festival: Festival, row: dict) -> Performance:
    """Choose the subclass once and resolve saved slugs into objects."""

    venue = festival.find_venue(row["venue"])
    if venue is None:
        raise NotFoundError(f"No venue {row['venue']!r}.")
    classes = {"solo": SoloShow, "lineup": Lineup, "workshop": Workshop}
    kind = row["kind"]
    if kind not in classes:
        raise InvalidValueError(f"Unknown performance kind {kind!r}.")
    performance_class = classes[kind]
    fields = {}
    if kind == "solo":
        fields = {
            "artist": festival.artist(row["artist"]),
            "min_age": row.get("min_age", 0),
        }
    elif kind == "lineup":
        if not isinstance(row["acts"], list):
            raise InvalidValueError("A lineup needs a list of act slugs.")
        fields = {
            "host": festival.artist(row["host"]),
            "acts": [festival.artist(slug) for slug in row["acts"]],
        }
    elif kind == "workshop":
        if not isinstance(row.get("participants", []), list):
            raise InvalidValueError("A workshop needs a list of participant names.")
        fields = {
            "teacher": festival.artist(row["teacher"]),
            "max_participants": row["max_participants"],
            "participants": row.get("participants", []),
        }
    return performance_class(
        title=row["title"],
        venue=venue,
        start=parse_moment(row["start"]),
        duration_minutes=row["duration_minutes"],
        description=row.get("description", ""),
        **fields,
    )


def festival_from_data(data: dict) -> Festival:
    """Build a fresh object graph, applying every rule while loading."""

    try:
        if not isinstance(data, dict):
            raise InvalidValueError("The data file must contain a festival object.")
        for key in ("venues", "artists", "performances"):
            if not isinstance(data.get(key), list):
                raise InvalidValueError(f"The data file needs a list of {key}.")
        festival = Festival(
            data["name"],
            parse_day(data["first_day"]),
            parse_day(data["last_day"]),
            [Venue(**row) for row in data["venues"]],
            [Artist(**row) for row in data["artists"]],
        )
        for row in data["performances"]:
            festival.add(performance_from_data(festival, row))
        return festival
    except KeyError as error:
        raise InvalidValueError(
            f"The data file is missing the field {error.args[0]!r}."
        ) from None
    except TypeError as error:
        raise InvalidValueError(
            f"The data file contains an invalid value: {error}."
        ) from None


class JsonStorage(FestivalStorage):
    """Load validated JSON and replace the saved file atomically."""

    def __init__(self, path: str | Path, seed: Path | None = None) -> None:
        self.path = Path(path)
        self.seed = seed

    def load(self) -> Festival:
        source = self.path if self.path.exists() or self.seed is None else self.seed
        try:
            with source.open(encoding="utf-8") as file:
                return festival_from_data(json.load(file))
        except json.JSONDecodeError as error:
            raise StorageError(
                f"The festival data file is damaged (line {error.lineno})."
            ) from None
        except (OSError, UnicodeError, FestivalError) as error:
            raise StorageError(f"Cannot read the festival data: {error}") from None

    def save(self, festival: Festival) -> None:
        festival.validate()
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(festival.to_saved(), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.path)
        except (OSError, UnicodeError) as error:
            raise StorageError(f"Cannot save the festival data: {error}") from None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


class MemoryStorage(FestivalStorage):
    """Keep independent festival snapshots in memory for tests."""

    def __init__(self, festival: Festival) -> None:
        self._data = deepcopy(festival.to_saved())

    def load(self) -> Festival:
        return festival_from_data(deepcopy(self._data))

    def save(self, festival: Festival) -> None:
        festival.validate()
        self._data = deepcopy(festival.to_saved())


def default_storage() -> JsonStorage:
    """Use local data, or the packaged edition until the first saved change."""

    return JsonStorage(
        Path.cwd() / "data" / "festival.json",
        seed=Path(__file__).parent / "data" / "festival.json",
    )
