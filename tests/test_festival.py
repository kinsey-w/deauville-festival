import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from deauville.errors import StorageError
from deauville.festival import Festival
from deauville.models import Artist, Lineup, SoloShow, Venue, Workshop
from deauville.service import FestivalService
from deauville.storage import JsonStorage


# E08 - The festival holds the rules, and tests prove it
@pytest.fixture
def festival() -> Festival:
    return Festival(
        "Test festival",
        date(2027, 6, 10),
        date(2027, 6, 13),
        [Venue("Room A", 100, "Address A"), Venue("Room B", 80, "Address B")],
        [Artist("Alice"), Artist("Bob"), Artist("Camille"), Artist("Diane")],
    )


def solo(
    festival: Festival,
    start: str = "2027-06-11T20:00",
    duration: float = 60,
    venue: str = "room-a",
    artist: str = "alice",
) -> SoloShow:
    return SoloShow(
        title="Test show",
        venue=festival.venue(venue),
        start=datetime.fromisoformat(start),
        duration_minutes=duration,
        artist=festival.artist(artist),
    )


@pytest.mark.parametrize(
    "start",
    [
        "2027-06-11T19:00",
        "2027-06-11T19:59",
        "2027-06-11T20:00",
        "2027-06-11T21:00",
        "2027-06-11T21:29",
    ],
)
def test_venue_gap_rejects_overlap_and_short_gaps(
    festival: Festival, start: str
) -> None:
    festival.add(solo(festival))
    before = festival.performances
    with pytest.raises(ValueError, match="busy"):
        festival.add(solo(festival, start=start, artist="bob"))
    assert festival.performances == before


@pytest.mark.parametrize("start", ["2027-06-11T18:30", "2027-06-11T21:30"])
def test_exact_thirty_minute_venue_gap_is_allowed(
    festival: Festival, start: str
) -> None:
    festival.add(solo(festival))
    festival.add(solo(festival, start=start, artist="bob"))
    assert len(festival.performances) == 2


@pytest.mark.parametrize(
    "start", ["2027-06-11T19:00", "2027-06-11T20:00", "2027-06-11T21:29"]
)
def test_artist_gap_applies_across_venues(festival: Festival, start: str) -> None:
    festival.add(solo(festival))
    with pytest.raises(ValueError, match="Alice is on stage"):
        festival.add(solo(festival, start=start, venue="room-b"))


def test_exact_thirty_minute_artist_gap_is_allowed(festival: Festival) -> None:
    festival.add(solo(festival))
    festival.add(solo(festival, start="2027-06-11T21:30", venue="room-b"))


@pytest.mark.parametrize("role", ["host", "act", "teacher"])
def test_artist_busy_in_every_role(festival: Festival, role: str) -> None:
    if role == "teacher":
        existing = Workshop(
            title="Workshop",
            venue=festival.venue("room-a"),
            start=datetime.fromisoformat("2027-06-11T20:00"),
            duration_minutes=60,
            teacher=festival.artist("alice"),
            max_participants=10,
        )
    else:
        existing = Lineup(
            title="Lineup",
            venue=festival.venue("room-a"),
            start=datetime.fromisoformat("2027-06-11T20:00"),
            duration_minutes=60,
            host=festival.artist("alice" if role == "host" else "bob"),
            acts=[
                festival.artist("alice" if role == "act" else "camille"),
                festival.artist("diane"),
            ],
        )
    festival.add(existing)
    with pytest.raises(ValueError, match="Alice is on stage"):
        festival.add(solo(festival, venue="room-b"))


@pytest.mark.parametrize(
    "start, day",
    [
        ("2027-06-12T01:00", date(2027, 6, 11)),
        ("2027-06-12T05:59", date(2027, 6, 11)),
        ("2027-06-12T06:00", date(2027, 6, 12)),
    ],
)
def test_festival_day_boundary(festival: Festival, start: str, day: date) -> None:
    show = solo(festival, start=start)
    festival.add(show)
    assert show.festival_day == day
    assert festival.programme(day) == [show]


@pytest.mark.parametrize("start", ["2027-06-10T05:59", "2027-06-14T06:00"])
def test_show_outside_festival_is_rejected(festival: Festival, start: str) -> None:
    with pytest.raises(ValueError, match="not a day of the festival"):
        festival.add(solo(festival, start=start))
    assert not festival.performances


def test_final_festival_night_is_allowed(festival: Festival) -> None:
    festival.add(solo(festival, start="2027-06-14T05:00"))
    assert festival.performances[0].festival_day == date(2027, 6, 13)


@pytest.mark.parametrize("duration", [0, 361, -1, True, 1.5])
def test_invalid_duration_is_rejected(festival: Festival, duration: float) -> None:
    with pytest.raises(ValueError, match="1 to 360"):
        solo(festival, duration=duration)


@pytest.mark.parametrize("duration", [1, 360])
def test_valid_duration_limits(festival: Festival, duration: float) -> None:
    festival.add(solo(festival, duration=duration))


def test_unknown_venue_is_rejected(festival: Festival) -> None:
    show = replace(solo(festival), venue=Venue("Unknown", 100, "Address"))
    with pytest.raises(ValueError, match="No venue 'unknown'"):
        festival.add(show)
    assert not festival.performances


@pytest.mark.parametrize("role", ["solo", "host", "act", "teacher"])
def test_unknown_artist_is_rejected_in_every_role(
    festival: Festival, role: str
) -> None:
    unknown = Artist("Unknown")
    base = solo(festival)
    if role == "solo":
        show = replace(base, artist=unknown)
    elif role == "teacher":
        show = Workshop(
            title=base.title,
            venue=base.venue,
            start=base.start,
            duration_minutes=base.duration_minutes,
            teacher=unknown,
            max_participants=10,
        )
    else:
        show = Lineup(
            title=base.title,
            venue=base.venue,
            start=base.start,
            duration_minutes=base.duration_minutes,
            host=unknown if role == "host" else festival.artist("bob"),
            acts=[
                unknown if role == "act" else festival.artist("camille"),
                festival.artist("diane"),
            ],
        )
    with pytest.raises(ValueError, match="No artist 'unknown'"):
        festival.add(show)


def test_sorting_uses_start_then_venue_name(festival: Festival) -> None:
    b = solo(festival, venue="room-b", artist="bob")
    a = solo(festival)
    festival.add(b)
    festival.add(a)
    assert festival.programme() == [a, b]
    assert sorted([b, a]) == [a, b]
    assert str(a) == "20:00-21:00 | Room A | Test show (solo)"


def test_artist_and_venue_identity_use_slug() -> None:
    assert Artist("Élodie Marchal", "First bio") == Artist(
        "Elodie Marchal", "Other bio"
    )
    assert Venue("Théâtre", 100, "A") == Venue("Theatre", 200, "B")
    assert Artist("Alice") != Artist("Bob")


def test_on_stage_includes_start_and_excludes_end(festival: Festival) -> None:
    show = solo(festival)
    festival.add(show)
    assert festival.on_stage(datetime.fromisoformat("2027-06-11T20:00")) == [show]
    assert festival.on_stage(datetime.fromisoformat("2027-06-11T21:00")) == []


def test_next_shows_are_sorted_limited_and_exclude_current(festival: Festival) -> None:
    for hour in [16, 10, 14, 12]:
        festival.add(solo(festival, start=f"2027-06-11T{hour}:00"))
    assert [
        show.start.hour
        for show in festival.up_next(datetime.fromisoformat("2027-06-11T09:00"))
    ] == [
        10,
        12,
        14,
    ]
    assert [
        show.start.hour
        for show in festival.up_next(datetime.fromisoformat("2027-06-11T10:00"))
    ] == [12, 14, 16]
    assert not festival.up_next(datetime.fromisoformat("2027-06-12T00:00"))


def test_public_collection_cannot_be_used_to_append(festival: Festival) -> None:
    assert isinstance(festival.performances, tuple)
    with pytest.raises(AttributeError):
        festival.performances.append(solo(festival))


def test_cancel_unknown_id_and_success(festival: Festival) -> None:
    show = solo(festival)
    festival.add(show)
    with pytest.raises(ValueError, match="No performance"):
        festival.cancel("missing")
    assert festival.cancel(show.id) == show.title
    assert not festival.performances


def test_save_reload_cancel_round_trip(festival: Festival, tmp_path: Path) -> None:
    path = tmp_path / "festival.json"
    show = solo(festival)
    storage = JsonStorage(path)
    storage.save(festival)
    FestivalService(storage).add(show.to_saved())
    loaded = JsonStorage(path).load()
    assert len(loaded.performances) == 1
    FestivalService(JsonStorage(path)).cancel(show.id)
    assert not JsonStorage(path).load().performances


def test_failed_save_does_not_change_file_or_schedule(
    festival: Festival, tmp_path: Path
) -> None:
    path = tmp_path / "festival.json"
    JsonStorage(path).save(festival)
    original = path.read_bytes()
    show = solo(festival)
    with (
        patch(
            "deauville.storage.os.replace",
            side_effect=PermissionError("Cannot replace"),
        ),
        pytest.raises(StorageError),
    ):
        FestivalService(JsonStorage(path)).add(show.to_saved())
    assert not festival.performances
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_loading_checks_conflicts_again(festival: Festival, tmp_path: Path) -> None:
    show = solo(festival)
    festival.add(show)
    data = festival.to_saved()
    data["performances"].append(show.to_saved())
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="busy"):
        JsonStorage(path).load()


def test_real_festival_now_examples() -> None:
    festival = JsonStorage(
        Path(__file__).resolve().parents[1] / "data/festival.json"
    ).load()
    at = datetime.fromisoformat("2027-06-11T21:00")
    assert [show.title for show in festival.on_stage(at)] == ["Tall Tales"]
    assert [show.title for show in festival.up_next(at)] == [
        "Straight Face",
        "Late Laughs",
        "After Hours",
    ]
    assert [
        show.title
        for show in festival.on_stage(datetime.fromisoformat("2027-06-12T01:30"))
    ] == ["After Hours"]
