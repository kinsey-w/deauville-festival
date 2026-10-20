import json
import re
import sys

from festival import (
    add_performance,
    artist_performances,
    cancel_performance,
    festival_days,
    find_artist,
    load_festival,
    on_stage,
    performance_from_data,
    programme,
    up_next,
)
from models import Performance, parse_day, parse_moment


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
        print(f"{venue.slug}: {venue.name}, {venue.capacity} seats")
        total_seats += venue.capacity
    print(f"Total: {total_seats} seats")


# E04 - Real dates and times
def performance_line(performance: Performance, role: str) -> str:
    return (
        f"{performance.start:%H:%M}-{performance.end:%H:%M} | "
        f"{performance.venue.name} | {performance.title} ({role})"
    )


def print_programme(festival: dict, day: str) -> None:
    requested_day = parse_day(day)
    days = festival_days(festival)
    if requested_day not in days:
        raise ValueError(
            f"No performance on {day!r}. Days: {', '.join(str(day) for day in days)}"
        )
    print(f"Programme for {requested_day:%A %d %B}:")
    for performance in programme(festival, requested_day):
        print(performance_line(performance, performance.kind))


def print_artist(festival: dict, slug: str) -> None:
    artist = find_artist(festival, slug)
    if artist is None:
        raise ValueError(f"No artist {slug!r}.")
    print(artist.name)
    for performance, role in artist_performances(festival, slug):
        print(f"{performance.festival_day:%a %d} {performance_line(performance, role)}")


def print_now(festival: dict, moment: str) -> None:
    at = parse_moment(moment)
    print(f"On stage at {at:%Y-%m-%d %H:%M}:")
    for performance in on_stage(festival, at):
        print(
            f"- {performance.title} at {performance.venue.name}, until {performance.end:%H:%M}"
        )
    print("Up next:")
    for performance in up_next(festival, at):
        print(f"- {performance_line(performance, performance.kind)}")


def ask_solo() -> dict:
    title = input("Title: ").strip()
    artist = input("Artist (slug): ").strip()
    venue = input("Venue (slug): ").strip()
    start = input("Start (YYYY-MM-DDTHH:MM): ").strip()
    duration = input("Duration (minutes): ").strip()
    if not re.fullmatch(r"[+-]?[0-9]+", duration):
        raise ValueError(f"{duration!r} is not a number of minutes.")
    return {
        "kind": "solo",
        "title": title,
        "artist": artist,
        "venue": venue,
        "start": start,
        "duration_minutes": int(duration),
        "description": "",
        "min_age": 0,
    }


# E03 - Functions and commands
def print_usage() -> None:
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist SLUG")
    print("  uv run main.py now YYYY-MM-DDTHH:MM")
    print("  uv run main.py add")
    print("  uv run main.py cancel ID")


def run_command() -> None:
    args = sys.argv[1:]
    if not (
        not args
        or args in (["venues"], ["add"])
        or (len(args) == 2 and args[0] in ("programme", "artist", "now", "cancel"))
    ):
        print_usage()
        raise ValueError(
            "Unknown command or wrong number of arguments; use the commands above."
        )
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
    elif args[0] == "add":
        new = performance_from_data(festival, ask_solo())
        add_performance(festival, new)
        print(f"Added: {new.id}")
    elif args[0] == "cancel":
        print(f"Cancelled: {cancel_performance(festival, args[1])}")


# E05 - Rules, errors and saving
def main() -> None:
    try:
        run_command()
    except json.JSONDecodeError as error:
        print(f"Error: The festival data file is damaged (line {error.lineno}).")
        sys.exit(1)
    except UnicodeError:
        print("Error: The festival data file must use UTF-8 text.")
        sys.exit(1)
    except FileNotFoundError as error:
        print(f"Error: File or folder {error.filename!r} was not found.")
        sys.exit(1)
    except OSError as error:
        print(f"Error: Cannot read or save the festival data: {error.strerror}.")
        sys.exit(1)
    except EOFError:
        print("Error: Input ended before all show details were provided.")
        sys.exit(1)
    except (ValueError, TypeError) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
