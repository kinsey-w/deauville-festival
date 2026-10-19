import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path


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
        festival = json.load(file)
    validate_festival(festival)
    return festival


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
    return parse_moment(performance["start"])


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
    requested_day = parse_day(day)
    days = festival_days(festival)
    if requested_day not in days:
        raise ValueError(
            f"No performance on {day!r}. Days: {', '.join(str(day) for day in days)}"
        )
    print(f"Programme for {requested_day:%A %d %B}:")
    for performance in programme(festival, requested_day):
        print(performance_line(festival, performance, performance["kind"]))


def print_artist(festival: dict, slug: str) -> None:
    artist = find_artist(festival, slug)
    if artist is None:
        raise ValueError(f"No artist {slug!r}.")
    print(artist["name"])
    for performance, role in artist_performances(festival, slug):
        print(
            f"{festival_day(performance):%a %d} {performance_line(festival, performance, role)}"
        )


def print_now(festival: dict, moment: str) -> None:
    at = parse_moment(moment)
    print(f"On stage at {at:%Y-%m-%d %H:%M}:")
    for performance in on_stage(festival, at):
        venue = find_venue(festival, performance["venue"])
        print(
            f"- {performance['title']} at {venue['name']}, until {end_of(performance):%H:%M}"
        )
    print("Up next:")
    for performance in up_next(festival, at):
        print(f"- {performance_line(festival, performance, performance['kind'])}")


# E05 - Rules, errors and saving
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


def stage_artists(performance: dict) -> list:
    if performance["kind"] == "solo":
        return [performance["artist"]]
    if performance["kind"] == "lineup":
        return [performance["host"]] + performance["acts"]
    if performance["kind"] == "workshop":
        return [performance["teacher"]]
    raise ValueError(f"Unknown performance kind {performance['kind']!r}.")


def performance_id(performance: dict) -> str:
    return f"{performance['venue']}-{start_of(performance):%Y-%m-%d-%H%M}"


def check_performance(festival: dict, new: dict) -> None:
    if not isinstance(new["title"], str) or not new["title"].strip():
        raise ValueError("A performance needs a non-empty title.")
    venue = find_venue(festival, new["venue"])
    if venue is None:
        raise ValueError(f"No venue {new['venue']!r}.")
    duration = new["duration_minutes"]
    if type(duration) is not int or not 1 <= duration <= 360:
        raise ValueError("Duration must be a whole number from 1 to 360 minutes.")
    day = festival_day(new)
    if not parse_day(festival["first_day"]) <= day <= parse_day(festival["last_day"]):
        raise ValueError(f"{day} is not a day of the festival.")
    artists = stage_artists(new)
    for slug in artists:
        if find_artist(festival, slug) is None:
            raise ValueError(f"No artist {slug!r}.")
    gap = timedelta(minutes=30)
    for other in festival["performances"]:
        if start_of(new) < end_of(other) + gap and start_of(other) < end_of(new) + gap:
            if new["venue"] == other["venue"]:
                raise ValueError(
                    f"{venue['name']} is busy with {other['title']} "
                    f"({start_of(other):%Y-%m-%d %H:%M}-{end_of(other):%H:%M}). "
                    "Leave 30 minutes between two shows."
                )
            for slug in artists:
                if slug in stage_artists(other):
                    artist = find_artist(festival, slug)
                    raise ValueError(
                        f"{artist['name']} is on stage in {other['title']}. "
                        "Leave 30 minutes between two shows."
                    )


def validate_festival(festival: dict) -> None:
    if not isinstance(festival, dict):
        raise TypeError("The data file must contain a festival object.")
    for key in ("name", "first_day", "last_day"):
        if not isinstance(festival.get(key), str) or not festival[key].strip():
            raise ValueError(f"The data file needs a non-empty {key!r}.")
    if parse_day(festival["first_day"]) > parse_day(festival["last_day"]):
        raise ValueError("The festival's first day must not follow its last day.")
    for key in ("venues", "artists", "performances"):
        if not isinstance(festival.get(key), list):
            raise TypeError(f"The data file needs a list of {key}.")
    for key in ("venues", "artists"):
        slugs = []
        for item in festival[key]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not slugify(item["name"])
            ):
                raise ValueError(f"Every entry in {key} needs a name.")
            slug = slugify(item["name"])
            if slug in slugs:
                raise ValueError(f"Duplicate {key} identifier {slug!r}.")
            slugs.append(slug)
            if key == "venues":
                if type(item.get("capacity")) is not int or item["capacity"] < 1:
                    raise ValueError(f"{item['name']} needs at least one seat.")
                if not isinstance(item.get("address"), str):
                    raise ValueError(f"{item['name']} needs an address.")
    checked = dict(festival, performances=[])
    for performance in festival["performances"]:
        if not isinstance(performance, dict):
            raise TypeError("Every performance in the data file must be an object.")
        fields = {"title": str, "venue": str, "start": str, "kind": str}
        for key, value_type in fields.items():
            if not isinstance(performance.get(key), value_type):
                raise TypeError(f"A performance needs a text {key!r}.")
        if "duration_minutes" not in performance:
            raise ValueError(f"{performance['title']} needs a duration_minutes value.")
        roles = {"solo": ("artist",), "lineup": ("host",), "workshop": ("teacher",)}
        if performance["kind"] not in roles:
            raise ValueError(f"Unknown performance kind {performance['kind']!r}.")
        for role in roles[performance["kind"]]:
            if not isinstance(performance.get(role), str):
                raise TypeError(f"{performance['title']} needs a {role} slug.")
        if performance["kind"] == "lineup":
            acts = performance.get("acts")
            if not isinstance(acts, list) or any(
                not isinstance(act, str) for act in acts
            ):
                raise ValueError(f"{performance['title']} needs a list of act slugs.")
        check_performance(checked, performance)
        checked["performances"].append(performance)


def save_festival(festival: dict, path: str = "data/festival.json") -> None:
    validate_festival(festival)
    destination = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(festival, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def add_performance(
    festival: dict, new: dict, path: str = "data/festival.json"
) -> None:
    new = dict(new, title=new["title"].strip())
    check_performance(festival, new)
    updated = dict(festival, performances=festival["performances"] + [new])
    save_festival(updated, path)
    festival["performances"] = updated["performances"]


def cancel_performance(
    festival: dict, identifier: str, path: str = "data/festival.json"
) -> str:
    for performance in festival["performances"]:
        if performance_id(performance) == identifier:
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
            return performance["title"]
    raise ValueError(f"No performance {identifier!r}.")


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
        new = ask_solo()
        add_performance(festival, new)
        print(f"Added: {performance_id(new)}")
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
