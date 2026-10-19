import json
import sys
import unicodedata
from datetime import date, datetime, timedelta


# E03 - Functions and commands
def slugify(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = ""
    for char in plain.lower():
        if char.isalnum():
            slug += char
        elif not slug.endswith("-"):
            slug += "-"
    return slug.strip("-")


def load_festival(path: str = "data/festival.json") -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def find_venue(festival: dict, slug: str) -> dict | None:
    for venue in festival["venues"]:
        if slugify(venue["name"]) == slug:
            return venue
    return None


def find_artist(festival: dict, slug: str) -> dict | None:
    for artist in festival["artists"]:
        if slugify(artist["name"]) == slug:
            return artist
    return None


def artist_performances(festival: dict, slug: str) -> list:
    appearances = []
    for performance in festival["performances"]:
        if performance["kind"] == "solo" and performance["artist"] == slug:
            appearances.append((performance, "solo"))
        elif performance["kind"] == "lineup":
            if performance["host"] == slug:
                appearances.append((performance, "host"))
            elif slug in performance["acts"]:
                appearances.append((performance, "act"))
        elif performance["kind"] == "workshop" and performance["teacher"] == slug:
            appearances.append((performance, "teacher"))
    return sorted(
        appearances, key=lambda appearance: performance_order(appearance[0], festival)
    )


# E04 - Real dates and times
def start_of(performance: dict) -> datetime:
    return datetime.fromisoformat(performance["start"])


def end_of(performance: dict) -> datetime:
    return start_of(performance) + timedelta(minutes=performance["duration_minutes"])


def festival_day(performance: dict) -> date:
    return (start_of(performance) - timedelta(hours=6)).date()


def performance_order(performance: dict, festival: dict) -> tuple:
    venue = find_venue(festival, performance["venue"])
    return start_of(performance), venue["name"]


def festival_days(festival: dict) -> list:
    days = []
    for performance in festival["performances"]:
        day = festival_day(performance)
        if day not in days:
            days.append(day)
    return sorted(days)


def programme(festival: dict, day: date) -> list:
    performances = []
    for performance in festival["performances"]:
        if festival_day(performance) == day:
            performances.append(performance)
    return sorted(
        performances, key=lambda performance: performance_order(performance, festival)
    )


def on_stage(festival: dict, at: datetime) -> list:
    performances = []
    for performance in festival["performances"]:
        if start_of(performance) <= at < end_of(performance):
            performances.append(performance)
    return sorted(
        performances, key=lambda performance: performance_order(performance, festival)
    )


def up_next(festival: dict, at: datetime) -> list:
    performances = []
    for performance in festival["performances"]:
        if start_of(performance) > at:
            performances.append(performance)
    return sorted(
        performances, key=lambda performance: performance_order(performance, festival)
    )[:3]


# E00 - Start the project
def print_summary(festival: dict) -> None:
    print(festival["name"])
    print(f"From {festival['first_day']} to {festival['last_day']}")
    print(
        f"{len(festival['venues'])} venues, "
        f"{len(festival['artists'])} artists, "
        f"{len(festival['performances'])} performances"
    )


# E01 - Explore the data
def print_venues(festival: dict) -> None:
    total_seats = 0
    for venue in festival["venues"]:
        print(f"{slugify(venue['name'])}: {venue['name']}, {venue['capacity']} seats")
        total_seats += venue["capacity"]
    print(f"Total: {total_seats} seats")


# E04 - Real dates and times
def performance_line(festival: dict, performance: dict, role: str) -> str:
    venue = find_venue(festival, performance["venue"])
    return (
        f"{start_of(performance):%H:%M}-{end_of(performance):%H:%M} | "
        f"{venue['name']} | {performance['title']} ({role})"
    )


def print_programme(festival: dict, day: str) -> None:
    requested_day = date.fromisoformat(day)
    days = festival_days(festival)
    if requested_day not in days:
        print(f"No performance on {day!r}. Days: {', '.join(str(day) for day in days)}")
        return
    print(f"Programme for {requested_day:%A %d %B}:")
    for performance in programme(festival, requested_day):
        print(performance_line(festival, performance, performance["kind"]))


def print_artist(festival: dict, slug: str) -> None:
    artist = find_artist(festival, slug)
    if artist is None:
        print(f"No artist {slug!r}.")
        return
    print(artist["name"])
    for performance, role in artist_performances(festival, slug):
        print(
            f"{festival_day(performance):%a %d} {performance_line(festival, performance, role)}"
        )


def print_now(festival: dict, moment: str) -> None:
    at = datetime.fromisoformat(moment)
    print(f"On stage at {at:%Y-%m-%d %H:%M}:")
    for performance in on_stage(festival, at):
        venue = find_venue(festival, performance["venue"])
        print(
            f"- {performance['title']} at {venue['name']}, until {end_of(performance):%H:%M}"
        )
    print("Up next:")
    for performance in up_next(festival, at):
        print(f"- {performance_line(festival, performance, performance['kind'])}")


# E03 - Functions and commands
def print_usage() -> None:
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist SLUG")
    print("  uv run main.py now YYYY-MM-DDTHH:MM")


def main() -> None:
    args = sys.argv[1:]
    if not (
        not args
        or args == ["venues"]
        or (len(args) == 2 and args[0] in ("programme", "artist", "now"))
    ):
        print_usage()
        return
    festival = load_festival()
    if not args:
        print_summary(festival)
    elif args[0] == "venues":
        print_venues(festival)
    elif args[0] == "programme":
        print_programme(festival, args[1])
    elif args[0] == "artist":
        print_artist(festival, args[1])
    elif args[0] == "now":
        print_now(festival, args[1])


if __name__ == "__main__":
    main()
