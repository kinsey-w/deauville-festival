from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from festival import (
    artist_performances,
    find_artist,
    find_venue,
    load_festival,
    programme,
)
from models import parse_day

# E06 - The website lights up
app = FastAPI(title="Deauville Festival du Rire")
ROOT = Path(__file__).resolve().parent


def read_festival() -> dict:
    try:
        return load_festival(ROOT / "data" / "festival.json")
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(
            status_code=500, detail=f"Cannot read the festival data: {error}"
        ) from None


@app.get("/api/festival")
def festival_info() -> dict:
    festival = read_festival()
    last = parse_day(festival["last_day"])
    days = []
    day = parse_day(festival["first_day"])
    while day <= last:
        days.append(day.isoformat())
        day += timedelta(days=1)
    return {
        "name": festival["name"],
        "first_day": festival["first_day"],
        "last_day": festival["last_day"],
        "days": days,
    }


@app.get("/api/venues")
def list_venues() -> list[dict]:
    return [venue.to_view() for venue in read_festival()["venues"]]


@app.get("/api/artists")
def list_artists() -> list[dict]:
    artists = sorted(read_festival()["artists"], key=lambda artist: artist.slug)
    return [artist.to_view() for artist in artists]


# E07 - The programme, and the first classes
@app.get("/api/programme")
def list_programme(day: date | None = None, venue: str | None = None) -> list[dict]:
    festival = read_festival()
    if venue is not None and find_venue(festival, venue) is None:
        raise HTTPException(status_code=404, detail=f"No venue {venue!r}.")
    return [performance.to_view() for performance in programme(festival, day, venue)]


@app.get("/api/performances/{identifier}")
def read_performance(identifier: str) -> dict:
    for performance in read_festival()["performances"]:
        if performance.id == identifier:
            return performance.to_view()
    raise HTTPException(status_code=404, detail=f"No performance {identifier!r}.")


@app.get("/api/artists/{slug}")
def read_artist(slug: str) -> dict:
    festival = read_festival()
    artist = find_artist(festival, slug)
    if artist is None:
        raise HTTPException(status_code=404, detail=f"No artist {slug!r}.")
    return {
        **artist.to_view(),
        "performances": [
            performance.to_view()
            for performance, role in artist_performances(festival, slug)
        ],
    }


app.mount("/", StaticFiles(directory=ROOT / "web" / "public", html=True))
