from dataclasses import replace
from datetime import date, datetime, timedelta

from deauville.errors import (
    ConflictError,
    InvalidValueError,
    NotFoundError,
)
from deauville.models import (
    Artist,
    Performance,
    Venue,
    Workshop,
    clean_name,
)


# E08 - The festival holds the rules, and tests prove it
class Festival:
    """Own the collections and enforce cross-performance scheduling rules."""

    def __init__(
        self,
        name: str,
        first_day: date,
        last_day: date,
        venues: list[Venue],
        artists: list[Artist],
    ) -> None:
        self._name = clean_name(name)
        if first_day > last_day:
            raise InvalidValueError(
                "The festival's first day must not follow its last day."
            )
        self._first_day = first_day
        self._last_day = last_day
        self._venues = {}
        self._artists = {}
        self._performances = []
        for venue in venues:
            if venue.slug in self._venues:
                raise ConflictError(f"Duplicate venues identifier {venue.slug!r}.")
            self._venues[venue.slug] = venue
        for artist in artists:
            if artist.slug in self._artists:
                raise ConflictError(f"Duplicate artists identifier {artist.slug!r}.")
            self._artists[artist.slug] = artist

    @property
    def name(self) -> str:
        return self._name

    @property
    def first_day(self) -> date:
        return self._first_day

    @property
    def last_day(self) -> date:
        return self._last_day

    @property
    def venues(self) -> tuple[Venue, ...]:
        return tuple(self._venues.values())

    @property
    def artists(self) -> tuple[Artist, ...]:
        return tuple(sorted(self._artists.values(), key=lambda artist: artist.slug))

    @property
    def performances(self) -> tuple[Performance, ...]:
        return tuple(sorted(self._performances))

    @property
    def days(self) -> list[date]:
        return [
            self.first_day + timedelta(days=offset)
            for offset in range((self.last_day - self.first_day).days + 1)
        ]

    def find_venue(self, slug: str) -> Venue | None:
        return self._venues.get(slug)

    def find_artist(self, slug: str) -> Artist | None:
        return self._artists.get(slug)

    def venue(self, slug: str) -> Venue:
        venue = self.find_venue(slug)
        if venue is None:
            raise NotFoundError(f"No venue {slug!r}.")
        return venue

    def artist(self, slug: str) -> Artist:
        artist = self.find_artist(slug)
        if artist is None:
            raise NotFoundError(f"No artist {slug!r}.")
        return artist

    def performance(self, identifier: str) -> Performance:
        for performance in self._performances:
            if performance.id == identifier:
                return performance
        raise NotFoundError(f"No performance {identifier!r}.")

    def programme(
        self, day: date | None = None, venue: str | None = None
    ) -> list[Performance]:
        if venue is not None:
            self.venue(venue)
        return [
            performance
            for performance in self.performances
            if (day is None or performance.festival_day == day)
            and (venue is None or performance.venue.slug == venue)
        ]

    def artist_performances(self, slug: str) -> list:
        artist = self.artist(slug)
        return [
            (performance, performance.role_of(artist))
            for performance in self.performances
            if performance.involves(artist)
        ]

    def on_stage(self, at: datetime) -> list[Performance]:
        return [
            performance
            for performance in self.performances
            if performance.is_running(at)
        ]

    def up_next(self, at: datetime) -> list[Performance]:
        return [
            performance for performance in self.performances if performance.start > at
        ][:3]

    def _check(self, new: Performance, existing: list[Performance]) -> None:
        """Validate a show against festival dates and 30-minute scheduling gaps."""

        new.validate()
        self.venue(new.venue.slug)
        if not self.first_day <= new.festival_day <= self.last_day:
            raise ConflictError(f"{new.festival_day} is not a day of the festival.")
        for artist in new.artists:
            self.artist(artist.slug)
        gap = timedelta(minutes=30)
        for other in existing:
            if new.start < other.end + gap and other.start < new.end + gap:
                if new.venue.slug == other.venue.slug:
                    raise ConflictError(
                        f"{new.venue.name} is busy with {other.title} "
                        f"({other.start:%Y-%m-%d %H:%M}-{other.end:%H:%M}). "
                        "Leave 30 minutes between two shows."
                    )
                for artist in new.artists:
                    if other.involves(artist):
                        raise ConflictError(
                            f"{artist.name} is on stage in {other.title}. Leave 30 minutes between two shows."
                        )

    def validate(self) -> None:
        for index, performance in enumerate(self._performances):
            self._check(performance, self._performances[:index])

    def add(self, new: Performance) -> None:
        new = self._canonical(new)
        self._check(new, self._performances)
        self._performances.append(new)

    def cancel(self, identifier: str) -> str:
        performance = self.performance(identifier)
        self._performances = [
            other for other in self._performances if other is not performance
        ]
        return performance.title

    # E10 - The admin: writing through the API
    def _canonical(self, new: Performance) -> Performance:
        """Resolve outside references to the festival-owned venue and artists."""

        venue = self.venue(new.venue.slug)
        artists = {artist.slug: self.artist(artist.slug) for artist in new.artists}
        return new.with_references(venue, artists)

    def update(self, identifier: str, new: Performance) -> Performance:
        old = self.performance(identifier)
        new = self._canonical(new)
        remaining = [other for other in self._performances if other is not old]
        self._check(new, remaining)
        updated = [new if other is old else other for other in self._performances]
        self._performances = updated
        return new

    def register(self, identifier: str, name: str) -> Workshop:
        show = self.performance(identifier)
        if not isinstance(show, Workshop):
            raise InvalidValueError(f"{show.title} is not a workshop.")
        name = clean_name(name)
        if any(
            participant.casefold() == name.casefold()
            for participant in show.participants
        ):
            raise ConflictError(f"{name} is already registered in {show.title}.")
        if show.places_left == 0:
            raise ConflictError(f"{show.title} is full.")
        new = replace(show, participants=(*show.participants, name))
        return self.update(identifier, new)

    def add_artist(self, artist: Artist) -> Artist:
        if artist.slug in self._artists:
            raise ConflictError(f"Artist {artist.name!r} already exists.")
        self._artists = {**self._artists, artist.slug: artist}
        return artist

    def to_view(self) -> dict:
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "days": [day.isoformat() for day in self.days],
        }

    def to_saved(self) -> dict:
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [venue.to_saved() for venue in self.venues],
            "artists": [artist.to_saved() for artist in self._artists.values()],
            "performances": [
                performance.to_saved() for performance in self._performances
            ],
        }
