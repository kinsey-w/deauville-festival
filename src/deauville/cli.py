import argparse
import re
import sys

from deauville.errors import FestivalError, InvalidValueError
from deauville.festival import Festival
from deauville.models import Performance, parse_day, parse_moment
from deauville.service import FestivalService
from deauville.storage import FestivalStorage, JsonStorage, default_storage


# E00 - Start the project
def print_summary(festival: Festival) -> None:
    print(festival.name)
    print(f"From {festival.first_day} to {festival.last_day}")
    print(
        f"{len(festival.venues)} venues, "
        f"{len(festival.artists)} artists, "
        f"{len(festival.performances)} performances"
    )


# E01 - Explore the data
def print_venues(festival: Festival) -> None:
    total_seats = 0
    for venue in festival.venues:
        print(f"{venue.slug}: {venue.name}, {venue.capacity} seats")
        total_seats += venue.capacity
    print(f"Total: {total_seats} seats")


# E13 - Ship it
def print_artists(festival: Festival) -> None:
    """List every artist with appearances counted across all stage roles."""
    for artist in festival.artists:
        count = len(festival.artist_performances(artist.slug))
        print(f"{artist.slug}: {artist.name}, {count} show(s)")


# E04 - Real dates and times
def performance_line(performance: Performance, role: str) -> str:
    return performance.format_line(role)


def print_programme(festival: Festival, day: str) -> None:
    requested_day = parse_day(day)
    days = festival.days
    if requested_day not in days:
        raise InvalidValueError(
            f"No performance on {day!r}. Days: {', '.join(str(day) for day in days)}"
        )
    print(f"Programme for {requested_day:%A %d %B}:")
    for performance in festival.programme(requested_day):
        print(performance_line(performance, performance.kind))


def print_artist(festival: Festival, slug: str) -> None:
    artist = festival.find_artist(slug)
    if artist is None:
        raise InvalidValueError(f"No artist {slug!r}.")
    print(artist.name)
    for performance, role in festival.artist_performances(slug):
        print(f"{performance.festival_day:%a %d} {performance_line(performance, role)}")


def print_now(festival: Festival, moment: str) -> None:
    at = parse_moment(moment)
    print(f"On stage at {at:%Y-%m-%d %H:%M}:")
    for performance in festival.on_stage(at):
        print(
            f"- {performance.title} at {performance.venue.name}, until {performance.end:%H:%M}"
        )
    print("Up next:")
    for performance in festival.up_next(at):
        print(f"- {performance_line(performance, performance.kind)}")


def ask_solo() -> dict:
    title = input("Title: ").strip()
    artist = input("Artist (slug): ").strip()
    venue = input("Venue (slug): ").strip()
    start = input("Start (YYYY-MM-DDTHH:MM): ").strip()
    duration = input("Duration (minutes): ").strip()
    if not re.fullmatch(r"[+-]?[0-9]+", duration):
        raise InvalidValueError(f"{duration!r} is not a number of minutes.")
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
    print("  uv run deauville")
    print("  uv run deauville venues")
    print("  uv run deauville artists")
    print("  uv run deauville programme YYYY-MM-DD")
    print("  uv run deauville artist SLUG")
    print("  uv run deauville now YYYY-MM-DDTHH:MM")
    print("  uv run deauville add")
    print("  uv run deauville cancel ID")
    print("  uv run deauville serve [--host 127.0.0.1] [--port 8000]")
    print("  --data FILE selects another festival JSON file.")


# E11 - A real package
class CommandParser(argparse.ArgumentParser):
    """Report argument errors through the festival error family."""

    def error(self, message: str) -> None:
        raise InvalidValueError(message)


def run_command(
    argv: list[str] | None = None, storage: FestivalStorage | None = None
) -> None:
    """Dispatch a terminal command using an injected or selected storage."""

    parser = CommandParser(prog="deauville", description="Deauville Festival du Rire")
    parser.add_argument("--data", help="Festival JSON file")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("command", nargs="?", default="summary")
    parser.add_argument("argument", nargs="?")
    options = parser.parse_args(argv)
    args = (
        []
        if options.command == "summary" and options.argument is None
        else [options.command]
    )
    if options.argument is not None:
        args.append(options.argument)
    if not (
        not args
        or args in (["venues"], ["artists"], ["add"], ["serve"])
        or (len(args) == 2 and args[0] in ("programme", "artist", "now", "cancel"))
    ):
        print_usage()
        raise InvalidValueError(
            "Unknown command or wrong number of arguments; use the commands above."
        )
    if not 1 <= options.port <= 65535:
        raise InvalidValueError("Server port must be from 1 to 65535.")
    storage = (
        storage
        if storage is not None
        else (JsonStorage(options.data) if options.data else default_storage())
    )
    if args == ["serve"]:
        import uvicorn

        from deauville.api import create_app

        uvicorn.run(create_app(storage), host=options.host, port=options.port)
        return
    festival = storage.load()
    service = FestivalService(storage)
    if not args:
        print_summary(festival)
    elif args[0] == "venues":
        print_venues(festival)
    elif args[0] == "artists":
        print_artists(festival)
    elif args[0] == "programme":
        print_programme(festival, args[1])
    elif args[0] == "artist":
        print_artist(festival, args[1])
    elif args[0] == "now":
        print_now(festival, args[1])
    elif args[0] == "add":
        new = service.add(ask_solo())
        print(f"Added: {new.id}")
    elif args[0] == "cancel":
        print(f"Cancelled: {service.cancel(args[1])}")


# E05 - Rules, errors and saving
def main(argv: list[str] | None = None) -> None:
    try:
        run_command(argv)
    except EOFError:
        print("Error: Input ended before all show details were provided.")
        sys.exit(1)
    except FestivalError as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
