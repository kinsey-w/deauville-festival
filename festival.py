import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from models import Artist, Performance, Venue, parse_day, parse_moment


# E07 - The programme, and the first classes
def find_venue(festival: dict, slug: str) -> Venue | None:
    for venue in festival["venues"]:
        if venue.slug == slug:
            return venue
    return None


def find_artist(festival: dict, slug: str) -> Artist | None:
    for artist in festival["artists"]:
        if artist.slug == slug:
            return artist
    return None


def known_artist(festival: dict, slug: str) -> Artist:
    artist = find_artist(festival, slug)
    if artist is None:
        raise ValueError(f"No artist {slug!r}.")
    return artist


def performance_from_data(festival: dict, row: dict) -> Performance:
    venue = find_venue(festival, row["venue"])
    if venue is None:
        raise ValueError(f"No venue {row['venue']!r}.")
    fields = {}
    if row["kind"] == "solo":
        fields = {
            "artist": known_artist(festival, row["artist"]),
            "min_age": row.get("min_age", 0),
        }
    elif row["kind"] == "lineup":
        if not isinstance(row["acts"], list):
            raise ValueError("A lineup needs a list of act slugs.")
        fields = {
            "host": known_artist(festival, row["host"]),
            "acts": [known_artist(festival, slug) for slug in row["acts"]],
        }
    elif row["kind"] == "workshop":
        if not isinstance(row.get("participants", []), list):
            raise ValueError("A workshop needs a list of participant names.")
        fields = {
            "teacher": known_artist(festival, row["teacher"]),
            "max_participants": row["max_participants"],
            "participants": row.get("participants", []),
        }
    return Performance(
        kind=row["kind"],
        title=row["title"],
        venue=venue,
        start=parse_moment(row["start"]),
        duration_minutes=row["duration_minutes"],
        description=row.get("description", ""),
        **fields,
    )


def load_festival(path: str = "data/festival.json") -> dict:
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    try:
        if not isinstance(data, dict):
            raise TypeError("The data file must contain a festival object.")
        for key in ("venues", "artists", "performances"):
            if not isinstance(data.get(key), list):
                raise TypeError(f"The data file needs a list of {key}.")
        festival = {
            "name": data["name"],
            "first_day": data["first_day"],
            "last_day": data["last_day"],
            "venues": [Venue(**row) for row in data["venues"]],
            "artists": [Artist(**row) for row in data["artists"]],
            "performances": [],
        }
        for row in data["performances"]:
            festival["performances"].append(performance_from_data(festival, row))
        validate_festival(festival)
        return festival
    except KeyError as error:
        raise ValueError(
            f"The data file is missing the field {error.args[0]!r}."
        ) from None
    except TypeError as error:
        raise ValueError(f"The data file contains an invalid value: {error}.") from None


def artist_performances(festival: dict, slug: str) -> list:
    artist = known_artist(festival, slug)
    appearances = []
    for performance in festival["performances"]:
        role = performance.role_of(artist)
        if role is not None:
            appearances.append((performance, role))
    return sorted(appearances, key=lambda appearance: performance_order(appearance[0]))


def performance_order(performance: Performance) -> tuple:
    return performance.start, performance.venue.name


# E04 - Real dates and times
def festival_days(festival: dict) -> list:
    days = []
    for performance in festival["performances"]:
        if performance.festival_day not in days:
            days.append(performance.festival_day)
    return sorted(days)


def programme(
    festival: dict, day: date | None = None, venue: str | None = None
) -> list:
    performances = []
    for performance in festival["performances"]:
        if (day is None or performance.festival_day == day) and (
            venue is None or performance.venue.slug == venue
        ):
            performances.append(performance)
    return sorted(performances, key=performance_order)


def on_stage(festival: dict, at: datetime) -> list:
    return [
        performance for performance in programme(festival) if performance.is_running(at)
    ]


def up_next(festival: dict, at: datetime) -> list:
    return [
        performance for performance in programme(festival) if performance.start > at
    ][:3]


# E05 - Rules, errors and saving
def check_performance(festival: dict, new: Performance) -> None:
    if find_venue(festival, new.venue.slug) is None:
        raise ValueError(f"No venue {new.venue.slug!r}.")
    if (
        not parse_day(festival["first_day"])
        <= new.festival_day
        <= parse_day(festival["last_day"])
    ):
        raise ValueError(f"{new.festival_day} is not a day of the festival.")
    for artist in new.artists:
        known_artist(festival, artist.slug)
    gap = timedelta(minutes=30)
    for other in festival["performances"]:
        if new.start < other.end + gap and other.start < new.end + gap:
            if new.venue.slug == other.venue.slug:
                raise ValueError(
                    f"{new.venue.name} is busy with {other.title} "
                    f"({other.start:%Y-%m-%d %H:%M}-{other.end:%H:%M}). "
                    "Leave 30 minutes between two shows."
                )
            for artist in new.artists:
                if other.involves(artist):
                    raise ValueError(
                        f"{artist.name} is on stage in {other.title}. Leave 30 minutes between two shows."
                    )


def validate_festival(festival: dict) -> None:
    if not isinstance(festival.get("name"), str) or not festival["name"].strip():
        raise ValueError("The data file needs a non-empty name.")
    if parse_day(festival["first_day"]) > parse_day(festival["last_day"]):
        raise ValueError("The festival's first day must not follow its last day.")
    for key in ("venues", "artists"):
        slugs = []
        for item in festival[key]:
            if item.slug in slugs:
                raise ValueError(f"Duplicate {key} identifier {item.slug!r}.")
            slugs.append(item.slug)
    checked = dict(festival, performances=[])
    for performance in festival["performances"]:
        check_performance(checked, performance)
        checked["performances"].append(performance)


def save_festival(festival: dict, path: str = "data/festival.json") -> None:
    validate_festival(festival)
    data = {
        "name": festival["name"],
        "first_day": festival["first_day"],
        "last_day": festival["last_day"],
    }
    for key in ("venues", "artists", "performances"):
        data[key] = [item.to_saved() for item in festival[key]]
    destination = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def add_performance(
    festival: dict, new: Performance, path: str = "data/festival.json"
) -> None:
    check_performance(festival, new)
    updated = dict(festival, performances=festival["performances"] + [new])
    save_festival(updated, path)
    festival["performances"] = updated["performances"]


def cancel_performance(
    festival: dict, identifier: str, path: str = "data/festival.json"
) -> str:
    for performance in festival["performances"]:
        if performance.id == identifier:
            updated = dict(
                festival,
                performances=[
                    other
                    for other in festival["performances"]
                    if other is not performance
                ],
            )
            save_festival(updated, path)
            festival["performances"] = updated["performances"]
            return performance.title
    raise ValueError(f"No performance {identifier!r}.")
