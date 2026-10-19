import json
import sys
import unicodedata


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
    return appearances


# E02 - The programme of a day
def festival_days(festival: dict) -> list:
    days = []
    for performance in festival["performances"]:
        day = performance["start"][:10]
        if day not in days:
            days.append(day)
    return sorted(days)


def programme(festival: dict, day: str) -> list:
    performances = []
    for performance in festival["performances"]:
        if performance["start"][:10] == day:
            performances.append(performance)
    return performances


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


# E02 - The programme of a day
def print_programme(festival: dict, day: str) -> None:
    days = festival_days(festival)
    if day not in days:
        print(f"No performance on {day!r}. Days: {', '.join(days)}")
        return
    print(f"Programme for {day}:")
    for performance in programme(festival, day):
        venue = find_venue(festival, performance["venue"])
        print(
            f"{performance['start'][11:]} | {venue['name']} | "
            f"{performance['title']} ({performance['kind']})"
        )


# E03 - Functions and commands
def print_artist(festival: dict, slug: str) -> None:
    artist = find_artist(festival, slug)
    if artist is None:
        print(f"No artist {slug!r}.")
        return
    print(artist["name"])
    for performance, role in artist_performances(festival, slug):
        venue = find_venue(festival, performance["venue"])
        start = performance["start"].replace("T", " ")
        print(f"{start} | {venue['name']} | {performance['title']} ({role})")


def print_usage() -> None:
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist SLUG")


def main() -> None:
    args = sys.argv[1:]
    if not (
        not args
        or args == ["venues"]
        or (len(args) == 2 and args[0] in ("programme", "artist"))
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


if __name__ == "__main__":
    main()
