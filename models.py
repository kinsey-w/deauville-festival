import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


# E07 - The programme, and the first classes
def slugify(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = ""
    for char in plain.lower():
        if char.isalnum():
            slug += char
        elif not slug.endswith("-"):
            slug += "-"
    return slug.strip("-")


def parse_day(text: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{text!r} is not a day, use YYYY-MM-DD.") from None


def parse_moment(text: str) -> datetime:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text):
            raise ValueError
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"{text!r} is not a local date and time, use YYYY-MM-DDTHH:MM."
        ) from None


def clean_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Names and titles must be non-empty text.")
    return value.strip()


@dataclass
class Venue:
    name: str
    capacity: int
    address: str

    def __post_init__(self) -> None:
        self.name = clean_name(self.name)
        if not self.slug:
            raise ValueError("A venue name needs letters or digits.")
        if type(self.capacity) is not int or self.capacity < 1:
            raise ValueError(f"{self.name} needs at least one seat.")
        if not isinstance(self.address, str):
            raise TypeError(f"{self.name} needs an address.")

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_saved(self) -> dict:
        return {"name": self.name, "capacity": self.capacity, "address": self.address}

    def to_view(self) -> dict:
        return {"slug": self.slug, **self.to_saved()}


@dataclass
class Artist:
    name: str
    bio: str = ""
    photo_url: str = ""

    def __post_init__(self) -> None:
        self.name = clean_name(self.name)
        if not self.slug:
            raise ValueError("An artist name needs letters or digits.")
        if not isinstance(self.bio, str) or not isinstance(self.photo_url, str):
            raise TypeError(f"{self.name}: biography and photo URL must be text.")

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_saved(self) -> dict:
        return {"name": self.name, "bio": self.bio, "photo_url": self.photo_url}

    def to_view(self) -> dict:
        return {"slug": self.slug, **self.to_saved()}


@dataclass
class Performance:
    kind: str
    title: str
    venue: Venue
    start: datetime
    duration_minutes: int
    description: str = ""
    artist: Artist | None = None
    min_age: int = 0
    host: Artist | None = None
    acts: list[Artist] = field(default_factory=list)
    teacher: Artist | None = None
    max_participants: int | None = None
    participants: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = clean_name(self.title)
        if self.kind not in ("solo", "lineup", "workshop"):
            raise ValueError(f"Unknown performance kind {self.kind!r}.")
        if not isinstance(self.venue, Venue):
            raise TypeError("A performance needs a known venue.")
        if not isinstance(self.start, datetime) or self.start.tzinfo is not None:
            raise ValueError(
                "A performance needs a local start time without a time zone."
            )
        if (
            type(self.duration_minutes) is not int
            or not 1 <= self.duration_minutes <= 360
        ):
            raise ValueError("Duration must be a whole number from 1 to 360 minutes.")
        if not isinstance(self.description, str):
            raise TypeError("A performance description must be text.")
        if self.kind == "solo":
            if not isinstance(self.artist, Artist):
                raise ValueError("A solo show needs a known artist.")
            if type(self.min_age) is not int or not 0 <= self.min_age <= 18:
                raise ValueError("Minimum audience age must be from 0 to 18.")
        elif self.kind == "lineup":
            if not isinstance(self.host, Artist) or any(
                not isinstance(act, Artist) for act in self.acts
            ):
                raise ValueError("A lineup needs a known host and artists.")
        elif self.kind == "workshop":
            if not isinstance(self.teacher, Artist):
                raise ValueError("A workshop needs a known teacher.")
            if type(self.max_participants) is not int or self.max_participants < 1:
                raise ValueError("A workshop needs at least one participant place.")
            self.participants = [clean_name(name) for name in self.participants]

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
    def artists(self) -> list[Artist]:
        if self.kind == "solo":
            return [self.artist]
        if self.kind == "lineup":
            return [self.host] + self.acts
        return [self.teacher]

    def role_of(self, artist: Artist) -> str | None:
        if self.kind == "solo" and self.artist.slug == artist.slug:
            return "solo"
        if self.kind == "lineup":
            if self.host.slug == artist.slug:
                return "host"
            if any(act.slug == artist.slug for act in self.acts):
                return "act"
        if self.kind == "workshop" and self.teacher.slug == artist.slug:
            return "teacher"
        return None

    def involves(self, artist: Artist) -> bool:
        return self.role_of(artist) is not None

    @property
    def capacity(self) -> int:
        if self.kind == "workshop":
            return min(self.max_participants, self.venue.capacity)
        return self.venue.capacity

    @property
    def places_left(self) -> int:
        return self.capacity - len(self.participants)

    @property
    def summary(self) -> str:
        if self.kind == "solo":
            return f"with {self.artist.name}"
        if self.kind == "lineup":
            return f"hosted by {self.host.name}, with {', '.join(act.name for act in self.acts)}"
        return f"with {self.teacher.name}"

    def is_running(self, at: datetime) -> bool:
        return self.start <= at < self.end

    def to_saved(self) -> dict:
        data = {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "start": self.start.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }
        if self.kind == "solo":
            data.update(artist=self.artist.slug, min_age=self.min_age)
        elif self.kind == "lineup":
            data.update(host=self.host.slug, acts=[act.slug for act in self.acts])
        else:
            data.update(
                teacher=self.teacher.slug,
                max_participants=self.max_participants,
                participants=list(self.participants),
            )
        return data

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
            **({"places_left": self.places_left} if self.kind == "workshop" else {}),
        }
