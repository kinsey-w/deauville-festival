import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import ClassVar

from deauville.errors import ConflictError, InvalidValueError


# E07 - The programme, and the first classes
def slugify(name: str) -> str:
    """Remove accents and collapse non-alphanumeric separators into single dashes."""

    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = ""
    for char in plain.lower():
        if char.isalnum():
            slug += char
        elif not slug.endswith("-"):
            slug += "-"
    return slug.strip("-")


def parse_day(text: str) -> date:
    """Parse the exact calendar-day format and explain invalid input."""

    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise InvalidValueError(f"{text!r} is not a day, use YYYY-MM-DD.") from None


def parse_moment(text: str) -> datetime:
    """Parse a minute-precision local timestamp without a time zone."""

    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text):
            raise ValueError
        return datetime.fromisoformat(text)
    except ValueError:
        raise InvalidValueError(
            f"{text!r} is not a local date and time, use YYYY-MM-DDTHH:MM."
        ) from None


def clean_name(value: str) -> str:
    """Strip surrounding whitespace and reject empty names or titles."""

    if not isinstance(value, str) or not value.strip():
        raise InvalidValueError("Names and titles must be non-empty text.")
    return value.strip()


@dataclass(eq=False, frozen=True)
class Venue:
    """Immutable venue whose identity is its normalised name slug."""

    name: str
    capacity: int
    address: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", clean_name(self.name))
        if not self.slug:
            raise InvalidValueError("A venue name needs letters or digits.")
        if type(self.capacity) is not int or self.capacity < 1:
            raise InvalidValueError(f"{self.name} needs at least one seat.")
        if not isinstance(self.address, str):
            raise InvalidValueError(f"{self.name} needs an address.")

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Venue):
            return NotImplemented
        return self.slug == other.slug

    def to_saved(self) -> dict:
        return {"name": self.name, "capacity": self.capacity, "address": self.address}

    def to_view(self) -> dict:
        return {"slug": self.slug, **self.to_saved()}


@dataclass(eq=False, frozen=True)
class Artist:
    """Immutable artist whose identity is its normalised name slug."""

    name: str
    bio: str = ""
    photo_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", clean_name(self.name))
        if not self.slug:
            raise InvalidValueError("An artist name needs letters or digits.")
        if not isinstance(self.bio, str) or not isinstance(self.photo_url, str):
            raise InvalidValueError(
                f"{self.name}: biography and photo URL must be text."
            )

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Artist):
            return NotImplemented
        return self.slug == other.slug

    def to_saved(self) -> dict:
        return {"name": self.name, "bio": self.bio, "photo_url": self.photo_url}

    def to_view(self) -> dict:
        return {"slug": self.slug, **self.to_saved()}


# E09 - Three kinds of performances
@dataclass(kw_only=True, frozen=True)
class Performance(ABC):
    """Abstract immutable show with shared timing and view behaviour."""

    title: str
    venue: Venue
    start: datetime
    duration_minutes: int
    description: str = ""
    kind: ClassVar[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", clean_name(self.title))
        self.validate()

    def validate(self) -> None:
        clean_name(self.title)
        if not isinstance(self.venue, Venue):
            raise InvalidValueError("A performance needs a known venue.")
        if not isinstance(self.start, datetime) or self.start.tzinfo is not None:
            raise InvalidValueError(
                "A performance needs a local start time without a time zone."
            )
        if (
            type(self.duration_minutes) is not int
            or not 1 <= self.duration_minutes <= 360
        ):
            raise InvalidValueError(
                "Duration must be a whole number from 1 to 360 minutes."
            )
        if not isinstance(self.description, str):
            raise InvalidValueError("A performance description must be text.")

    def __lt__(self, other: Performance) -> bool:
        if not isinstance(other, Performance):
            return NotImplemented
        return (self.start, self.venue.name) < (other.start, other.venue.name)

    def __str__(self) -> str:
        return self.format_line()

    def format_line(self, role: str | None = None) -> str:
        return (
            f"{self.start:%H:%M}-{self.end:%H:%M} | "
            f"{self.venue.name} | {self.title} ({self.kind if role is None else role})"
        )

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self) -> date:
        return (self.start - timedelta(hours=6)).date()

    @property
    def id(self) -> str:
        return f"{self.venue.slug}-{self.start:%Y-%m-%d-%H%M}"

    @property
    @abstractmethod
    def artists(self) -> list[Artist]:
        """Return everyone on stage in order of appearance."""

    @abstractmethod
    def role_of(self, artist: Artist) -> str | None:
        """Return the artist's role, or None when absent."""

    @abstractmethod
    def with_references(self, venue: Venue, artists: dict[str, Artist]) -> Performance:
        """Return a copy referencing the festival's canonical venue and artists."""

    def involves(self, artist: Artist) -> bool:
        return self.role_of(artist) is not None

    @property
    def capacity(self) -> int:
        return self.venue.capacity

    @property
    @abstractmethod
    def summary(self) -> str:
        """Return a one-line description for this kind of show."""

    def is_running(self, at: datetime) -> bool:
        return self.start <= at < self.end

    def to_saved(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "start": self.start.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }

    def to_view(self) -> dict:
        return {
            **self.to_saved(),
            "id": self.id,
            "venue_name": self.venue.name,
            "end": self.end.isoformat(timespec="minutes"),
            "festival_day": self.festival_day.isoformat(),
            "summary": self.summary,
            "capacity": self.capacity,
            "artists": [
                {"slug": artist.slug, "name": artist.name} for artist in self.artists
            ],
        }


@dataclass(kw_only=True, frozen=True)
class SoloShow(Performance):
    """One artist with an audience age limit."""

    kind: ClassVar[str] = "solo"
    artist: Artist
    min_age: int = 0

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.artist, Artist):
            raise InvalidValueError("A solo show needs a known artist.")
        if type(self.min_age) is not int or not 0 <= self.min_age <= 18:
            raise InvalidValueError("Minimum audience age must be from 0 to 18.")

    @property
    def artists(self) -> list[Artist]:
        return [self.artist]

    def role_of(self, artist: Artist) -> str | None:
        return "solo" if self.artist == artist else None

    def with_references(self, venue: Venue, artists: dict[str, Artist]) -> Performance:
        return replace(self, venue=venue, artist=artists[self.artist.slug])

    @property
    def summary(self) -> str:
        return self.artist.name

    def to_saved(self) -> dict:
        return {
            **super().to_saved(),
            "artist": self.artist.slug,
            "min_age": self.min_age,
        }


@dataclass(kw_only=True, frozen=True)
class Lineup(Performance):
    """A host and ordered acts with a minimum running time."""

    kind: ClassVar[str] = "lineup"
    host: Artist
    acts: tuple[Artist, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.acts, (list, tuple)):
            raise InvalidValueError("A lineup needs a list of artists.")
        object.__setattr__(self, "acts", tuple(self.acts))
        super().__post_init__()

    def validate(self) -> None:
        super().validate()
        if (
            not isinstance(self.host, Artist)
            or not isinstance(self.acts, tuple)
            or any(not isinstance(act, Artist) for act in self.acts)
        ):
            raise InvalidValueError(
                "A lineup needs a known host and a list of artists."
            )
        if len(self.acts) < 2:
            raise InvalidValueError("A lineup needs at least two acts.")
        slugs = [act.slug for act in self.acts]
        if len(set(slugs)) != len(slugs):
            raise InvalidValueError(
                "Each artist may appear only once in the lineup acts."
            )
        if self.host.slug in slugs:
            raise InvalidValueError("The lineup host cannot also be an act.")
        minimum = len(self.acts) * 10 + (len(self.acts) - 1) * 3
        if self.duration_minutes < minimum:
            raise InvalidValueError(
                f"A lineup of {len(self.acts)} acts needs at least {minimum} minutes."
            )

    @property
    def artists(self) -> list[Artist]:
        return [self.host, *self.acts]

    def role_of(self, artist: Artist) -> str | None:
        if self.host == artist:
            return "host"
        return "act" if artist in self.acts else None

    def with_references(self, venue: Venue, artists: dict[str, Artist]) -> Performance:
        return replace(
            self,
            venue=venue,
            host=artists[self.host.slug],
            acts=tuple(artists[act.slug] for act in self.acts),
        )

    @property
    def summary(self) -> str:
        return f"hosted by {self.host.name}, with {', '.join(act.name for act in self.acts)}"

    def to_saved(self) -> dict:
        return {
            **super().to_saved(),
            "host": self.host.slug,
            "acts": [act.slug for act in self.acts],
        }


@dataclass(kw_only=True, frozen=True)
class Workshop(Performance):
    """A teacher and named registrations within venue-limited capacity."""

    kind: ClassVar[str] = "workshop"
    teacher: Artist
    max_participants: int
    participants: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.participants, (list, tuple)):
            raise InvalidValueError("Workshop participants must be a list of names.")
        object.__setattr__(
            self, "participants", tuple(clean_name(name) for name in self.participants)
        )
        super().__post_init__()

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.teacher, Artist):
            raise InvalidValueError("A workshop needs a known teacher.")
        if type(self.max_participants) is not int or self.max_participants < 1:
            raise InvalidValueError("A workshop needs at least one participant place.")
        if not isinstance(self.participants, tuple):
            raise InvalidValueError("Workshop participants must be a list of names.")
        names = [clean_name(name) for name in self.participants]
        if len({name.casefold() for name in names}) != len(names):
            raise ConflictError("A participant is already registered in this workshop.")
        if len(names) > self.capacity:
            raise ConflictError(f"The workshop has only {self.capacity} places.")

    @property
    def artists(self) -> list[Artist]:
        return [self.teacher]

    def role_of(self, artist: Artist) -> str | None:
        return "teacher" if self.teacher == artist else None

    def with_references(self, venue: Venue, artists: dict[str, Artist]) -> Performance:
        return replace(self, venue=venue, teacher=artists[self.teacher.slug])

    @property
    def capacity(self) -> int:
        return min(self.max_participants, self.venue.capacity)

    @property
    def places_left(self) -> int:
        return self.capacity - len(self.participants)

    @property
    def summary(self) -> str:
        return f"with {self.teacher.name}, {len(self.participants)}/{self.capacity} places taken"

    def to_saved(self) -> dict:
        return {
            **super().to_saved(),
            "teacher": self.teacher.slug,
            "max_participants": self.max_participants,
            "participants": list(self.participants),
        }

    def to_view(self) -> dict:
        return {**super().to_view(), "places_left": self.places_left}
